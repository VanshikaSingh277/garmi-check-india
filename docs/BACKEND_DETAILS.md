> **Detail reference only.** `docs/BACKEND_SPEC.md` overrides this file wherever they differ. The main overrides:
> - **Where people's details are stored:** for self-managed homes they stay on the phone (spec §5.1, §5.3). In the `chronic` migration, keep the condition "unspecified", not `heart` (spec §5.3).
> - **Weather cells and jobs:** cells are 0.1° plus an elevation bucket, and prefetch runs only at 17:30 and 05:30 (spec §4, §9). The database file never goes in `data/` (spec §4).
> - **`phone_hash`:** must be an HMAC (spec §5.4).
> - **`notice_log` unique key:** spec §5.9.
> - **OTP table and limits:** spec §5.5, §6.6.
> - **Worker sessions, orgs and access logs:** spec §5.10, §6.7.
> - **Rate limits:** spec §8.7.
> - **Calibration outlier rule:** spec §7.4.
> - **Alert rules:** fatigue, and the IMD Yellow mapping (spec §7.1, §7.6).
> - **Build order and phase numbers:** section 8 below is replaced by spec §12.

# Thandak Backend: What to Implement (fields, tables, endpoints, jobs)

Written 24 Oct 2026, against `heat-india` at merge commit `a4f574e` (main + vanshika/fixes).

**Goal:** a thin backend that adds what the phone can't do on its own:
- evening alerts
- saved households
- assisted mode for ASHA, anganwadi and NGO workers
- learning each home from thermometer readings
- official IMD warnings
- anonymous numbers for government

The existing stateless endpoints stay as they are. Anyone can still use the app without saving anything.

---

## 0. Already done (don't rebuild)

| Exists | Where |
|---|---|
| Heat level from weather + IMD rules only. Home factors are listed beside it, not added to it. Includes the plains/hill/coastal heat-wave rules and 1991–2020 normals. | `engine/rules.py`, `engine/normals.py` |
| Fix catalogue (31 fixes), with triggers, conditions, budget, humidity and climate | `data/fixes.json`, `engine/solutions.py` |
| Questions: roof, vulnerable people, devices, roof access, cross-ventilation, budget | `IndividualIn` in `main.py` |
| Measure a fix at home (before/after readings, kept on the device) | `POST /api/fix_effect`, `GET /api/outdoor`, `web/src/views/measure.js` |
| Offline last result | `gc_last` in the browser |
| Tests: API, recommend, rules, heat level, i18n, India | `tests/` |

---

## 1. Infrastructure to add

| Item | Choice | Why |
|---|---|---|
| Database | **SQLite** (one file, WAL mode) now → **Postgres** when you run more than one server | It fits the one-container deploy. Use SQLAlchemy/SQLModel so switching later is a config change. |
| Migrations | **Alembic** | Schema changes without losing data |
| Scheduler | **APScheduler** inside the app, *or* an external cron calling `POST /internal/jobs/{name}` | Runs the evening alerts and other daily jobs |
| HTTP client | **httpx** (async), with retries | Replaces blocking `urllib` in `weather.py` |
| Cache | In-process `TTLCache` now → **Redis** with more than one server | A shared forecast cache cuts Open-Meteo calls |
| Push | **Firebase Cloud Messaging** (Android/iOS via `@capacitor/push-notifications`) + **Web Push (VAPID)** for the website | Delivers the alerts |
| SMS / WhatsApp | One Indian provider (e.g. Gupshup, MSG91 or Twilio). Needs DLT template registration for SMS. | Reaches people without smartphones |
| Errors / metrics | Sentry (or similar) + `/internal/metrics` | Shows failures, especially during heat waves |

### Environment variables

| Name | Example | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/thandak.db` | Database |
| `REDIS_URL` | *(empty)* | Optional shared cache |
| `TOKEN_PEPPER` | random 32 bytes | Hashing household and worker tokens |
| `FCM_CREDENTIALS_JSON` | path or JSON | App push |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | — | Web push |
| `SMS_PROVIDER`, `SMS_API_KEY`, `SMS_SENDER_ID`, `SMS_DLT_ENTITY_ID` | — | SMS |
| `WHATSAPP_API_KEY`, `WHATSAPP_NUMBER_ID`, `WHATSAPP_WEBHOOK_SECRET` | — | WhatsApp |
| `IMD_API_BASE`, `IMD_API_KEY` | — | Official warnings (after IMD onboarding) |
| `WEATHER_PROVIDER` | `open_meteo` | Switch provider without code changes |
| `OPEN_METEO_API_KEY` | *(empty on free tier)* | Paid plan for production |
| `INTERNAL_JOB_SECRET` | random | Protects `/internal/*` |
| `PHONE_ENC_KEY` | 32-byte key | Encrypts phone numbers at rest |
| `ALERT_HOUR_IST` | `19` | Evening alert time |
| `RETENTION_DAYS_INACTIVE` | `365` | Auto-delete inactive households |
| `AGG_MIN_COUNT` | `10` | Smallest group shown in government numbers |
| `THANDAK_ORIGINS` | *(exists)* | CORS |

---

## 2. Database tables and fields

All ids are UUIDs and all times are stored in UTC. Only the place is stored rounded.

### 2.1 `household`

The saved home. There is **no login**: the phone keeps a secret token.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `token_hash` | text, unique | SHA-256(token + pepper). The raw token is shown only once, at creation. |
| `created_at`, `updated_at`, `last_seen_at` | timestamptz | `last_seen_at` drives the retention purge |
| `lang` | enum `en`, `hi` (more later) | |
| `lat_r`, `lon_r` | numeric(5,2) | **Rounded to 0.01° (~1 km)**. The exact GPS is never stored. |
| `place_label`, `district_id`, `district`, `state`, `ward_no` | text | From `where_info` at save time |
| `roof` | enum: same values as `ROOFS` in `main.py` | |
| `roof_access` | bool | |
| `cross_ventilation` | bool, nullable | Already asked |
| `budget` | text | Same band values as `solutions.budget_band` |
| `tenure` | enum `own`, `rent`, `other`, nullable | **New question.** Renters get "ask your landlord" for roof fixes. |
| `floor_level` | smallint, nullable | **New question (optional)** |
| `fan`, `cooler`, `ac` | bool | |
| `power_cuts` | bool, nullable | **New question** |
| `power_cut_hours` | jsonb, e.g. `[["14:00","16:00"]]` | The plan assumes no fan/cooler/AC in these hours |
| `water_short` | bool, nullable | **New question.** Changes the bath / wet-cloth advice. |
| `alerts_enabled` | bool, default false | Opt-in |
| `alert_hour_ist` | smallint, default 19 | |
| `alert_min_level` | enum `high`, `extreme`, default `high` | |
| `consent_version` | text | E.g. `2026-11-v1` |
| `consent_at` | timestamptz | |
| `consent_by` | enum `self`, `worker` | `worker` = assisted mode, with verbal consent recorded |
| `worker_id` | uuid FK → `worker`, nullable | Set when an ASHA/NGO worker manages this home |
| `calib_bias_c` | real, default 0 | Cached result of §4.3 |
| `calib_n` | int, default 0 | |
| `calib_sd_c` | real, nullable | |
| `deleted_at` | timestamptz, nullable | Soft delete, hard-deleted by the purge job within 24 h |

### 2.2 `person`

One row per person who needs care. Healthy adults don't need a row.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `household_id` | uuid FK, cascade delete | |
| `label` | text, max 30, nullable | A nickname like "Dadi". **Never require a real name.** |
| `age_band` | enum `infant_0_1`, `child_1_5`, `child_6_14`, `adult_15_64`, `older_65_74`, `older_75_plus` | Picks the fan group and the health card |
| `pregnant` | bool | |
| `conditions` | text[], values `heart`, `kidney`, `diabetes`, `respiratory`, `mental_health`, `bedridden` | **Classes only, no diagnoses** |
| `medicine_classes` | text[], values `water_pill`, `bp_ace_arb`, `anticholinergic`, `psychiatric`, `other` | Classes only, never drug names. `anticholinergic` → 37 °C fan limit (`fan.limit.anticholinergic`, already verified). |
| `lives_alone` | bool | Triggers daily check-in advice and the worker brief |
| `outdoor_work` | bool | |
| `work_start`, `work_end` | time, nullable | For these hours, use the outdoor heat index for this person |
| `work_type` | enum `construction`, `vendor`, `delivery`, `farm`, `traffic`, `other`, nullable | |

> **Migration from today's form:** today's `vulnerable` list maps to persons. `elderly` → `older_65_74`, `child` → `child_1_5`, `pregnant` → `adult_15_64` with `pregnant=true`, `chronic` → `conditions=["heart"]`, set as "unspecified", and `outdoor_worker` → `outdoor_work=true`. The stateless `/api/status/individual` keeps accepting the old list.

### 2.3 `push_target`

Where to send alerts.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `household_id` *or* `worker_id` | uuid FK | Exactly one is set |
| `kind` | enum `fcm`, `webpush`, `sms`, `whatsapp`, `voice` | |
| `fcm_token` | text | For `fcm` |
| `endpoint`, `p256dh`, `auth` | text | For `webpush` |
| `phone_enc` | bytea | For sms / whatsapp / voice; AES-GCM with `PHONE_ENC_KEY` |
| `phone_hash` | text | To find duplicates and handle STOP without decrypting |
| `created_at`, `last_ok_at` | timestamptz | |
| `fail_count` | int | Disable after 5 failures in a row |
| `active` | bool | |

### 2.4 `reading`

Room thermometer readings used to learn the home.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `household_id` | uuid FK | |
| `ts` | timestamptz | Rounded to the hour to match the forecast |
| `room` | enum `bedroom`, `living`, `kitchen`, `other` | |
| `indoor_c` | real | Rejected if outside 10–55 °C |
| `outdoor_c` | real | From the cached forecast for that hour, filled in by the server |
| `predicted_c` | real, nullable | The model's estimate for that hour, with the household's settings at the time |
| `source` | enum `thermometer`, `ac_remote`, `logger`, `other` | |
| `accepted` | bool | False if \|indoor − predicted\| > 8 °C (likely a typo or the thermometer was in the sun) |
| `fix_id` | text, nullable | Links to a fix being measured (replaces the device-only storage in `measure.js` when the household is saved) |

### 2.5 `feedback`

| Field | Type | Notes |
|---|---|---|
| `household_id`, `for_date` | PK together | One answer per day |
| `night_feel` | enum `fine`, `hot`, `could_not_sleep` | |
| `followed_plan` | enum `yes`, `partly`, `no`, nullable | |
| `anyone_unwell` | bool, nullable | Answering yes shows the warning-signs card and 112. **Not a medical record.** |
| `created_at` | timestamptz | |

No free text is stored, so there's no hidden personal data.

### 2.6 `fix_progress`

| Field | Type | Notes |
|---|---|---|
| `household_id`, `fix_id` | PK together | `fix_id` comes from `fixes.json` |
| `status` | enum `planned`, `done`, `not_possible` | |
| `done_at` | date, nullable | |
| `measured_effect_c` | real, nullable | From `solutions.estimate_fix_effect` |
| `measured_n` | int, nullable | |

### 2.7 `notice_log`

Every alert attempt.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `household_id` / `worker_id` | uuid FK | |
| `for_date` | date | The day the alert is about |
| `kind` | enum `evening`, `morning_work`, `imd_warning`, `worker_brief`, `test` | |
| `level` | enum | The level that triggered it |
| `person_ids` | uuid[] | Who it is about |
| `channel` | enum (as `push_target.kind`) | |
| `template_id`, `lang` | text | |
| `status` | enum `queued`, `sent`, `failed`, `opened`, `skipped_duplicate` | |
| `error` | text, nullable | |
| `queued_at`, `sent_at`, `opened_at` | timestamptz | `opened_at` comes from the app opening with `?n=<id>` |

Unique on (`household_id`, `for_date`, `kind`), so a household gets **at most one alert per kind per day**.

### 2.8 `org` and `worker` (assisted mode)

| `org` field | Type |
|---|---|
| `id` | uuid PK |
| `name` | text |
| `type` | enum `health_dept`, `ngo`, `rwa`, `school`, `other` |
| `state`, `district_id` | text |
| `created_at` | timestamptz |

| `worker` field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid FK | |
| `role` | enum `asha`, `anganwadi`, `ngo`, `volunteer`, `org_admin` | |
| `display_name` | text | |
| `phone_enc`, `phone_hash` | bytea, text | Used for OTP login |
| `token_hash` | text | Session token |
| `district_id` | text | |
| `active` | bool | |
| `created_at`, `last_seen_at` | timestamptz | |

### 2.9 `forecast_cache`

Only needed without Redis.

| Field | Type |
|---|---|
| `cell` | text PK, e.g. `"28.61,77.21"` |
| `provider` | text |
| `fetched_at` | timestamptz |
| `payload` | json (hourly rows, as `weather.fetch` returns) |

### 2.10 `imd_warning`

| Field | Type | Notes |
|---|---|---|
| `district_id`, `for_date`, `phenomenon` | PK together | `phenomenon` = `heat_wave`, `warm_night`, `hot_humid` |
| `color` | enum `green`, `yellow`, `orange`, `red` | |
| `issued_at`, `fetched_at` | timestamptz | |
| `source_url` | text | |

**Rule:** our level is never shown below IMD's level. Orange means at least High, and Red means Extreme. The reason code is `imd_district_warning`.

### 2.11 `daily_aggregate`

Numbers for government, with no personal data.

| Field | Type | Notes |
|---|---|---|
| `for_date`, `district_id` | PK together | |
| `households` | int | Saved homes in the district |
| `households_high`, `households_extreme` | int | |
| `people_older`, `people_infant`, `people_pregnant`, `people_outdoor_work` | int | Only in High/Extreme homes |
| `alerts_sent`, `alerts_opened` | int | |
| `nights_could_not_sleep` | int | |

**Any count below `AGG_MIN_COUNT` (10) is stored as NULL**, so no single household can be identified.

### 2.12 `consent_event`

Proof of consent (DPDP Act 2023).

| Field | Type |
|---|---|
| `id` | uuid PK |
| `household_id` / `worker_id` | uuid |
| `action` | enum `given`, `withdrawn`, `exported`, `deleted` |
| `consent_version` | text |
| `by` | enum `self`, `worker` |
| `at` | timestamptz |

`consent_event` is kept after a household is deleted, but holds no other data about it.

---

## 3. API endpoints

Use the `/api/v1` prefix for new endpoints. The existing ones stay as they are.
- **Household auth:** `Authorization: Bearer <household token>`
- **Worker auth:** `Authorization: Bearer <worker token>`

### 3.1 Household (saved home)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/api/v1/households` | `{consent:{version, accepted:true}, lang, place:{lat,lon}, home:{roof, roof_access, cross_ventilation, budget, tenure, floor_level, devices:{fan,cooler,ac}, power_cuts, power_cut_hours, water_short}, people:[Person], alerts:{enabled, hour_ist, min_level}}` | `{household_id, token}`. **The token is shown once.** The phone stores it. |
| GET | `/api/v1/households/me` | — | The saved household + people (exact GPS is not returned, because it was never stored) |
| PATCH | `/api/v1/households/me` | Any subset of the POST body | The updated household |
| DELETE | `/api/v1/households/me` | — | `204`. Deletes everything now: people, readings, feedback, push targets. Logs `consent_event: deleted`. |
| GET | `/api/v1/households/me/export` | — | All stored data as JSON (right of access) |
| POST | `/api/v1/households/me/people` | `Person` | The person |
| PATCH / DELETE | `/api/v1/households/me/people/{id}` | — | — |

`Person` = `{label?, age_band, pregnant, conditions[], medicine_classes[], lives_alone, outdoor_work, work_start?, work_end?, work_type?}`

### 3.2 Personal results

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/v1/households/me/status` | `day=today\|tomorrow` | Same body as `/api/status/individual` **plus** the fields below |
| GET | `/api/v1/households/me/outlook` | `days=5` (max 7) | Per day: `{date, level, reasons, hi_max, tmax, tmin, twb_max, imd_color?, room_peak_range?, persons_at_risk:[person_id]}` |

The extra fields on the status response are:
- `per_person: [{person_id, label, level, fan_group, fan_now, fan_avoid_hours, fan_not_enough_hours, work_hours_hot:[...], card_ids:[...]}]`
- `today_actions: [{code, text, hours?, person_ids?}]`
- `calibration: {bias_c, n, sd_c, applied:bool}`
- `imd_warning?`
- `fix_progress`

### 3.3 Readings, feedback, fixes

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/v1/households/me/readings` | `{ts?, room, indoor_c, source, fix_id?}` | The reading with `outdoor_c`, `predicted_c` and `accepted`, plus the new `calibration` |
| GET | `/api/v1/households/me/readings` | `?from&to` | A list of readings |
| DELETE | `/api/v1/households/me/readings/{id}` | — | `204`, then recompute the calibration |
| POST | `/api/v1/households/me/feedback` | `{for_date, night_feel, followed_plan?, anyone_unwell?}` | `204` |
| PUT | `/api/v1/households/me/fixes/{fix_id}` | `{status, done_at?}` | The progress row, with `measured_effect_c` if there are enough readings |

### 3.4 Push and messaging

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/v1/push` | `{kind:"fcm", token}` or `{kind:"webpush", endpoint, keys:{p256dh,auth}}` or `{kind:"sms"\|"whatsapp", phone}` | Phone numbers need an OTP first (§3.5) |
| DELETE | `/api/v1/push/{id}` | — | |
| POST | `/api/v1/push/test` | — | Sends one test alert (max 3 per day) |
| GET | `/api/v1/vapid-public-key` | — | For web push subscription |
| POST | `/api/v1/webhooks/whatsapp` | Provider payload | Handles `STOP` (unsubscribe), `HELP`, `ALERT`, and onboarding by PIN code ("send your PIN code to get heat alerts") |
| POST | `/api/v1/webhooks/sms-status` | Provider payload | Updates `notice_log.status` |

### 3.5 OTP (phones and workers)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/v1/otp/send` | `{phone, purpose:"household_sms"\|"worker_login"}` | Max 3 per hour per phone, 10 per day per IP |
| POST | `/api/v1/otp/verify` | `{phone, code, purpose}` | Returns a short-lived proof, or the worker token |

### 3.6 Assisted mode (ASHA, anganwadi and NGO workers)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/api/v1/orgs/{org_id}/workers` | `{display_name, phone, role}` (org_admin only) | Invites a worker |
| GET | `/api/v1/workers/me` | — | Profile, org, number of households |
| GET | `/api/v1/workers/me/households` | `?day=today\|tomorrow&min_level=high` | `[{household_id, label, place_label, level, persons_at_risk:[{label, age_band, why}], top_actions:[...], last_feedback}]`, sorted most at risk first |
| POST | `/api/v1/workers/me/households` | Household body (§3.1) + `consent:{version, by:"worker", verbal:true}` | Creates a household the worker manages (the family needs no phone) |
| PATCH / DELETE | `/api/v1/workers/me/households/{id}` | — | Worker edits, or removes the household on the family's request |
| GET | `/api/v1/workers/me/brief` | `?day=tomorrow&format=json\|text\|pdf` | A one-page list: who's at risk, what to tell them, who to visit first. `text` is ready for WhatsApp/SMS. |

### 3.7 Government (anonymous counts)

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/v1/gov/today` | `state?`, `district_id?`, `day?` | Rows from `daily_aggregate` (small counts are NULL) + the IMD colour per district |
| GET | `/api/v1/gov/trend` | `district_id`, `from`, `to` | Daily series |

### 3.8 System and internal

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` (extend it) | `{ok, time, db_ok, model_loaded, gazetteer_loaded, weather_last_ok_at, weather_provider, imd_last_ok_at}` |
| GET | `/api/version` | `{api, rules_version (verified_numbers hash), catalogue_version (fixes.json version), model_version (model card date)}`. The app shows it in About, and support can see which rules a user had. |
| POST | `/internal/jobs/{name}` | Header `X-Job-Secret`. Runs a job from §5 by hand or from cron. |
| GET | `/internal/metrics` | Requests, latency, cache hit rate, weather errors, alerts sent/failed |

### 3.9 Changes to existing endpoints

| Endpoint | Change |
|---|---|
| All | Validate `lang` / `roof` / `vulnerable` with Pydantic `Literal` types (422 errors, not silent drops) |
| `/api/status/individual` | Guard `start = next(...)` (it crashes with `StopIteration` today). Accept optional `people[]`, `tenure`, `power_cuts`, `power_cut_hours`, `water_short` so the not-saved flow gets the same personalisation. Add `per_person` and `today_actions`. |
| `/api/weather` | Add `stale: bool` and `provider` |
| `/api/gov/rank`, `/api/wards/list`, `/api/about` | Load the JSON once (`lru_cache`), not on every request |
| Startup | `@app.on_event("startup")` → `lifespan` |

---

## 4. Engine changes

### 4.1 Weather (`engine/weather.py` → `engine/providers/`)

- Define a `WeatherProvider` interface: `fetch(lat, lon, past_days, forecast_days) -> {hourly, daily, fetched_at, provider}`.
- Implement it with `OpenMeteoProvider` (as now) and later `ImdProvider`.
- Fetch **7 forecast days** (today it's 2), so the outlook and tomorrow's alert have data.
- Use async httpx with a 5 s timeout, 2 retries with backoff, and a TTL cache of 5 000 cells.
- **Serve stale on error:** if a fetch fails and the cache is under 6 h old, return it with `stale=true`.

### 4.2 Per-person rules (`engine/rules.py` + new `engine/people.py`)

The level stays weather-only (as main decided). What becomes per person is the **fan limits**, **work-hour exposure** and **health card**.

| Person | Fan group → limits (all from `verified_numbers.csv`) |
|---|---|
| `older_*` | `older`: 35 / 38 °C |
| has `anticholinergic` | `anticholinergic`: avoid fan alone from **37 °C** (`fan.limit.anticholinergic`, verified, unused today) |
| infant, child, pregnant, chronic condition, other medicines | `older` (precautionary, as now). Mark it `precautionary:true`. |
| otherwise | `adult`: 35 / 39 °C |

- **Household fan advice** uses the strictest person.
- **AC:** if `ac=true` and the hour is not a power-cut hour, change the fan state "avoid fan alone" to the action "use the AC this hour (24 °C)". Don't warn about fans in a room with a working AC.
- **Outdoor workers:** for `work_start`–`work_end`, use **outdoor** HI/Tmax. Produce `work_hours_hot` (the hours ≥ the High band) and the "shift work away from 12–3 pm" action (NCDC).
- **Power cuts:** for `power_cut_hours`, run `indoor.predict` with `fan=False, cooler=False`, and drop the AC action.

### 4.3 Room estimate fallback and per-home calibration (`engine/indoor.py`, new `engine/calibrate.py`)

**Fallback outside the training range.** Today, on the hottest days, no room estimate is given. Instead:
- Use outdoor + the measured roof offset for that hour (`roof.offset.*`, verified).
- Set `basis:"offset"` and widen the range.
- The window plan and fan states keep working.

**Calibration:** use a per-home bias with shrinkage.
- `bias = Σ(indoor_c − predicted_c) / (n + k)` over accepted readings from the last 30 days.
- `k` = within-home residual variance ÷ between-home variance of mean residuals, both computed once from the leave-home-out CV in `ml/indoor/`. Store it in the model card.
- Apply it only when `n ≥ 2`. Corrected estimate = model + bias.
- Band: when `n ≥ 5`, use the household's own residual p10/p90.
- **Validate before shipping:** replay held-out 2016 homes (first N readings → error on later days). Ship only if it improves MAE, and record the result in the model card.

### 4.4 Today actions (`engine/today.py`)

These are built from the forecast + household + people. Every number comes from the forecast or `verified_numbers.csv`. Example codes:

| Code | Trigger | Text pattern |
|---|---|---|
| `fan_not_safe_for_person` | A person's fan state = avoid during hours H | "{H}: room about {lo}–{hi} °C. A fan alone isn't safe for {label}. Use the cooler/AC or move them to the coolest room." |
| `use_ac_hours` | `ac` and room ≥ the not-enough limit | "Run the AC at 24 °C during {H}." |
| `close_windows` / `open_windows` | From `plan` | "Close windows and curtains {H}; open them {H2}." |
| `work_hours_hot` | Outdoor worker and HI ≥ High during work | "{label}: hottest work hours {H}. Rest in shade, drink water every 20 minutes, avoid 12–3 pm (NCDC)." |
| `power_cut_hot` | A power cut overlaps the hottest hours | "Power cut expected {H}, the hottest time. Pre-cool the room, keep water and a wet cloth ready." |
| `warm_night` | IMD warm-night rule, or room night minimum is high | "Tonight stays hot ({t} °C at 3 am). Sleep in the coolest room…" |
| `check_on_alone` | A person `lives_alone` and level ≥ High | "Call or visit {label} twice today." |
| `infant_care` | Infant and level ≥ High | "Feed the baby more often. Never leave a child in a parked vehicle." |
| `medicine_doctor` | Any `medicine_classes` and level ≥ High | "On {class} medicines? Don't stop them. Ask your doctor about heat and how much to drink." |
| `imd_warning` | IMD Orange/Red for the district | "IMD has issued a {color} heat warning for {district}." |

### 4.5 Alert decision (`engine/notify.py`)

- **Send an evening alert for tomorrow** if, for the household, `tomorrow.level ≥ alert_min_level`, **or** tomorrow is ≥ 1 level above today **and** ≥ Moderate, **or** IMD is Orange/Red.
- **Morning work alert** at 06:30 if a person has `outdoor_work` and today's work hours hit High.
- **Templates per language.** Push or SMS text **must not contain health details**: write "Tomorrow: Extreme heat at your home. Open Thandak for your plan", not "Dadi's heart medicine…". Details appear only inside the app, or in the worker brief.
- **Dedupe** using the `notice_log` unique key.
- **Quiet hours:** never send between 22:00 and 06:00 IST.

---

## 5. Background jobs

| Job | When (IST) | What |
|---|---|---|
| `prefetch_forecasts` | Every hour at :05 | Fetch the forecast for every distinct `(lat_r, lon_r)` of active households, so the evening run makes no live calls |
| `imd_warnings` | 14:30 and 20:30 (after IMD bulletins) | Pull district warnings → `imd_warning` |
| `evening_alerts` | Every 15 min, 18:00–21:00 | Households whose `alert_hour_ist` has arrived → decide (§4.5) → queue → send |
| `worker_brief` | 06:30 and 19:00 | Build and send each worker's list |
| `morning_work_alerts` | 06:30 | Outdoor workers whose hours are hot today |
| `send_queue` | Every minute | Send queued `notice_log` rows; retry with backoff; disable targets after 5 failures |
| `daily_aggregates` | 23:30 | Fill `daily_aggregate` (NULL below 10) |
| `retention_purge` | 03:00 | Hard-delete `deleted_at` rows; delete households with `last_seen_at` > 365 days; delete readings > 2 years old; delete OTPs > 1 day old |
| `recalibrate` | On each new reading, and nightly | Update `calib_*` |
| `backup` | 02:00 | SQLite `.backup` (or `pg_dump`) to object storage; keep 14 days |

---

## 6. Security and privacy rules

- **Tokens:** generate 32 random bytes, store only the SHA-256 hash with the pepper, and compare in constant time.
- **Never stored:** exact GPS (only 0.01°), real names (nicknames are optional), drug names (classes only), free-text health notes.
- **Phone numbers:** encrypted at rest (`phone_enc`), with a hash for lookup.
- **Logs:** no tokens, phone numbers or lat/lon beyond the 0.01° cell.
- **Rate limits** (e.g. `slowapi`):

  | Endpoint | Limit |
  |---|---|
  | `/api/status/*` | 60/min per IP |
  | `/api/v1/households` (POST) | 10/hour per IP |
  | OTP | As in §3.5 |
  | `/api/v1/push/test` | 3/day |

- **Consent** (DPDP Act 2023):
  - Before saving, show a plain Hindi/English notice listing what is stored, why, how long it is kept, and how to delete it.
  - Log every consent action in `consent_event`.
  - In assisted mode the worker confirms verbal consent, and the family can ask the worker to delete the data at any time.
- **Export and delete:** `GET /me/export` and `DELETE /me` must work in one tap from the app.
- **CORS:** keep the current allow-list. `/internal/*` needs the secret header and should also be blocked at the proxy.

---

## 7. Tests to add

| Test | Checks |
|---|---|
| `test_households.py` | Create → get → patch → delete; the token works only for its own household; delete removes all child rows; export has all fields |
| `test_people_rules.py` | Anticholinergic → 37 °C; infant → precautionary older limits; AC removes fan warnings; power-cut hours drop devices; outdoor worker uses outdoor HI in work hours |
| `test_calibration.py` | n=0 → bias 0; shrinkage with k; an outlier reading is rejected; the band narrows at n ≥ 5 |
| `test_offset_fallback.py` | Replay **28 May 2024 Delhi** (outdoor > 42 °C): a room estimate exists with `basis:"offset"`, and the window plan is not empty |
| `test_notify.py` | Alert rules; one per day; quiet hours; **no health words in the push text** |
| `test_worker.py` | A worker sees only their own households; brief sort order; consent_by=worker recorded |
| `test_aggregates.py` | Counts < 10 become NULL |
| `test_weather_provider.py` | Retry; stale fallback; 7-day fetch; provider switch |
| Recorded fixtures | Save Open-Meteo responses (Delhi, Chennai, Jaisalmer, the heat-wave day) under `tests/fixtures/`, so tests never call the internet |

---

## 8. Build order

| Phase | Items | Effort |
|---|---|---|
| 1. Make the current API solid | §3.9 fixes, §4.1 weather provider + 7 days + stale fallback, §4.3 offset fallback, fixtures and tests | 3 days |
| 2. Per-person advice (still no saving) | §4.2, §4.4 `today_actions`, extra optional fields on `/api/status/individual` | 3 days |
| 3. Saved households | DB + Alembic, §2.1–2.2 + 2.12, §3.1–3.2, consent screens, delete/export | 3 days |
| 4. Alerts | §2.3 + 2.7, §3.4, §4.5, jobs `prefetch_forecasts` / `evening_alerts` / `send_queue`, FCM + web push | 3 days |
| 5. Learn the home | §2.4–2.6, §3.3, §4.3 calibration + its validation | 3 days |
| 6. Assisted mode + WhatsApp/SMS | §2.8, §3.5–3.6, webhooks, `worker_brief` job | 4–5 days |
| 7. IMD + government numbers | §2.10–2.11, §3.7, `imd_warnings` + `daily_aggregates` jobs (IMD needs API onboarding first) | 3 days + IMD wait |
| 8. Ops | Sentry, metrics, backups, load test before summer | 2 days |

**New questions for the app**, all optional and with a "skip" choice:
- own/rent
- power cuts (yes/no + usual hours)
- water shortage
- for each person: age band, pregnant, condition and medicine **classes**, lives alone, outdoor work hours
