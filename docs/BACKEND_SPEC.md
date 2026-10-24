# Thandak backend spec

This is the single source of truth for the backend. It merges three documents:
- the implementation plan written against `heat-india` at commit `a4f574e`
- the earlier safety and security spec
- the fixes from reviewing both

It replaces `THANDAK_BACKEND_BUILD.md` and `REWORK_PROMPT.md`.

The original implementation plan is kept as `docs/BACKEND_DETAILS.md` for field-level detail; this file points to its sections as "DETAILS §x". Where the two disagree (storage of people, weather cells, jobs, limits, alert rules), **this file wins**. If anything else in the repo disagrees with this file, this file also wins; report the conflict.

Work one phase at a time (section 12). Commands are in `README.md`.

---

## 1. Goal

A thin backend that adds what the phone can't do on its own. In order of value:

1. **Evening heat alerts on WhatsApp and SMS.** Most people won't open an app, so alerts have to reach them.
2. **Advice for each person at home.** This works without saving anything.
3. **Saved households in the app.**
4. **Assisted mode** for ASHA, anganwadi and NGO workers.
5. **Learning each home** from thermometer readings.
6. **Official IMD warnings and anonymous numbers for government.**

The existing stateless endpoints stay, and anyone can use the app without saving anything.

## 2. Ground rules (every phase)

1. **Never invent** a heat or health number, a threshold, a source URL, a phone number, or the final wording of a consent notice or message template. Draft templates and notices, but mark them `DRAFT` for team approval. If something needed is missing:
   - add it to `docs/TEAM_TODO.md` (and add a `TO VERIFY` row if it is a number)
   - keep the feature that needs it off
   - list it in the phase report
2. **Every heat, health or effect number** shown to users or used in a rule comes from `verified_numbers.csv`, or from a data file listed in `data/MANIFEST.json`.
   - This includes numbers inside sentences: minutes, °C, hours, "twice a day".
   - Security and ops limits (OTP expiry, rate limits) live in config instead.
3. **Number status rules:**
   - Shown to users as a fact: `Verified` or `Computed` only.
   - Used in a safety rule: `Verified`, `Computed` or `Standard`.
   - A `Design choice` may only make a result more cautious.
   - `UNVERIFIED` and `TO VERIFY` are never used.
4. **The heat level comes only from weather and official warnings.**
   - Household and person factors never change it.
   - ML output never raises, lowers or gates a safety level.
   - Safety decisions use the cautious end of the room range.
5. **Store only what section 5.1 allows.** For self-managed homes, health details stay on the phone.
6. **All user-facing text exists in English and Hindi.**
   - Hindi drafts go in the review list.
   - Any English left inside a Hindi response is listed in `needs_translation`.
7. **Push, SMS and WhatsApp texts never contain health details.** That means no conditions, medicines, pregnancy or names, including in worker briefs.
8. **If this spec conflicts with existing safety code,** keep the stricter rule and report it.

## 3. Already done (verify in Phase 0, don't rebuild)

| Exists | Where |
|---|---|
| Heat level from weather + IMD rules only; home factors listed beside it. Plains/hill/coastal rules with 1991–2020 normals. | `engine/rules.py`, `engine/normals.py` |
| Fix catalogue (31 fixes) with triggers, conditions, budget, humidity and climate | `data/fixes.json`, `engine/solutions.py` |
| Questions: roof, vulnerable people, devices, roof access, cross-ventilation, budget | `IndividualIn` in `main.py` |
| Before/after readings, kept on the device | `POST /api/fix_effect`, `GET /api/outdoor`, `web/src/views/measure.js` |
| Offline last result | `gc_last` in the browser |
| Tests: API, recommend, rules, heat level, i18n, India | `tests/` |

In Phase 0, confirm two things and report what you find:
- that a severe heat wave (Tmax ≥ 47 °C on plains, or a departure above 6.4 °C) maps to Extreme
- that the heat-index band uses `max(air temperature, heat index)`

## 4. Architecture

| Item | Choice | Notes |
|---|---|---|
| Database | SQLite (WAL mode) now, Postgres later, through SQLAlchemy 2 and Alembic | Keep the file on its own writable volume (e.g. `/var/lib/thandak/`), never in `data/`. Use portable types only: no ARRAY or JSONB; use JSON columns or join tables. Store UUIDs as text and times in UTC. |
| Jobs | A separate process `python -m app.jobs` (APScheduler), or an external cron calling `POST /internal/jobs/{name}` | Never run jobs inside web workers. Every job takes a `job_lock` row and is idempotent. |
| HTTP client | Async httpx; 5 s timeout; 2 retries with backoff | Replaces the blocking `urllib` |
| Weather | `WeatherProvider` interface plus `OpenMeteoProvider`; 7 forecast days and 2 past days | A cell is lat/lon rounded to 0.1° plus a 100 m elevation bucket, sent as the `elevation` parameter |
| Cache | In-process TTL cache (≤ 5,000 cells) now; Redis once there is more than one server | Single-flight per cell; on error, serve data up to 6 h stale with `stale=true` |
| Upstream budget | `WEATHER_DAILY_BUDGET` | At 90%: no new cells; serve the nearest cached cell within 25 km (marked approximate) or basic mode |
| WhatsApp / SMS | One Indian provider; SMS needs DLT entity and template registration | Phase 2 |
| App push | FCM (`@capacitor/push-notifications`) + Web Push (VAPID) | Phase 4 |
| Errors / metrics | Sentry (or similar) with scrubbing (8.8); `/internal/metrics` | Phase 2, before any alert goes out |

Environment variables are listed in `env.example` (no leading dot, so tools that skip dotfiles still read it). Real values come from env or a secret store and are never committed.

| Name | Purpose |
|---|---|
| `ENV` | `dev` or `prod` |
| `DATABASE_URL` | Database |
| `REDIS_URL` | Optional shared cache and rate-limit store |
| `TOKEN_PEPPER` | Hashing household and worker tokens |
| `PHONE_ENC_KEYS` | Key ring (`id:key,…`) for AES-GCM phone encryption |
| `PHONE_HMAC_KEY` | Keyed hash for phone lookups |
| `PERSON_ENC_KEYS` | Key ring for worker-managed person fields |
| `LOG_HASH_SECRET` | HMAC for IPs in logs (rotated daily) |
| `FCM_CREDENTIALS_JSON` | App push |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | Web push |
| `SMS_PROVIDER`, `SMS_API_KEY`, `SMS_SENDER_ID`, `SMS_DLT_ENTITY_ID` | SMS |
| `WHATSAPP_API_KEY`, `WHATSAPP_NUMBER_ID`, `WHATSAPP_WEBHOOK_SECRET` | WhatsApp |
| `IMD_API_BASE`, `IMD_API_KEY` | Official warnings, after IMD onboarding |
| `WEATHER_PROVIDER`, `OPEN_METEO_API_KEY`, `WEATHER_DAILY_BUDGET` | Weather |
| `OTP_DAILY_CAP` | Global OTP limit per day |
| `INTERNAL_JOB_SECRET` | Protects `/internal/*` |
| `RETENTION_DAYS_INACTIVE` | Default 365 |
| `AGG_MIN_COUNT` | Default 10 |
| `ALERT_REPEAT_DAYS` | Default 3 (7.6) |
| `ROOM_MODEL_MODE` | `validated_only` (default) or `rough_guide` |
| `THANDAK_ORIGINS`, `ALLOWED_HOSTS`, `TRUSTED_PROXY_CIDRS`, `DOCS_ENABLED`, `SENTRY_DSN` | HTTP and ops |

## 5. Data model

### 5.1 What is stored, and where

| Data | Self-managed home | Worker-managed home |
|---|---|---|
| Area (0.1° cell, district), language, alert settings | Server | Server |
| Home settings: roof, devices, power cuts, water, tenure, budget | Server | Server |
| People: age band, pregnancy, condition and medicine classes, lives alone, work hours, nickname | **Phone only**, sent with each status request | Server, encrypted (5.3) |
| Alert summary: `higher_risk` flag, outdoor work window | Server | Server |
| Anonymous counts for government | Server, only if the family ticks "share anonymous counts" | Server |
| Readings, fix progress, daily feedback | Server | Server |
| Phone numbers | Server, encrypted + HMAC | Server, encrypted + HMAC |
| Exact GPS, real names, drug names, free-text notes, place label | Never (the place label stays on the phone) | Never |

### 5.2 `household`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `token_hash` | text, unique | SHA-256(token + pepper). The raw token is shown once. |
| `token_created_at`, `created_at`, `updated_at` | time | |
| `last_seen_at` | time | Updated by **any** interaction: an app call, a WhatsApp or SMS reply, or a worker visit |
| `lang` | enum `en`, `hi` | |
| `cell_lat`, `cell_lon` | decimal, 0.1° | The exact GPS is never stored |
| `elev_bucket_m` | int | 100 m buckets, from the gazetteer |
| `district_id`, `district`, `state`, `ward_no` | text | `ward_no` is nullable |
| `roof`, `roof_access`, `cross_ventilation`, `budget` | as the existing form | All nullable (WhatsApp sign-ups may not have them) |
| `tenure` | enum `own`, `rent`, `other`, nullable | Renters get "ask your landlord" for roof fixes |
| `floor_level` | int, nullable | |
| `fan`, `cooler`, `ac` | bool, nullable | |
| `power_cuts` | bool, nullable | |
| `power_cut_hours` | JSON, e.g. `[["14:00","16:00"]]` | |
| `water_short` | bool, nullable | |
| `higher_risk` | bool | Set by the phone or the worker. It is the only health-related bit stored for self-managed homes. |
| `outdoor_work_window` | JSON, nullable | For morning work alerts |
| `share_counts` | bool, default false | |
| `counts` | JSON, nullable | `{older, infant, child, pregnant, outdoor_worker}`, only when `share_counts` is true |
| `alerts_enabled` | bool, default false | Opt-in |
| `alert_hour_ist` | int, default 19 | |
| `alert_min_level` | enum `high`, `extreme` | |
| `managed_by` | enum `self`, `worker` | |
| `worker_id` | uuid FK, nullable | |
| `consent_version`, `consent_at` | | |
| `consent_by` | enum `self`, `worker` | |
| `calib_bias_day_c`, `calib_bias_night_c`, `calib_n_day`, `calib_n_night`, `calib_sd_c` | numbers | Section 7.4 |
| `deleted_at` | time, nullable | Soft delete; the purge job hard-deletes within 24 h |

### 5.3 `person` (worker-managed homes only)

Self-managed homes keep the same `Person` object on the phone and send it in request bodies. It is never stored for them.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `household_id` | uuid FK, cascade delete | |
| `label_enc` | bytes, nullable | Encrypted nickname, such as "Dadi". Never require a real name. |
| `age_band` | enum `infant_0_1`, `child_1_5`, `child_6_14`, `adult_15_64`, `older_65_74`, `older_75_plus` | |
| `pregnant` | bool | |
| `conditions_enc` | bytes | Encrypted JSON list of classes only: `heart`, `kidney`, `diabetes`, `respiratory`, `mental_health`, `bedridden` |
| `medicine_classes_enc` | bytes | Encrypted JSON list: `water_pill`, `bp_ace_arb`, `anticholinergic`, `psychiatric`, `other`. Never drug names. |
| `key_id` | text | Which `PERSON_ENC_KEYS` key encrypted this row |
| `lives_alone`, `outdoor_work` | bool | |
| `work_start`, `work_end` | time, nullable | |
| `work_type` | enum `construction`, `vendor`, `delivery`, `farm`, `traffic`, `other`, nullable | |

**Migration from today's form.** Map the old `vulnerable` list like this:
- `elderly` → `older_65_74`
- `child` → `child_1_5`
- `pregnant` → `adult_15_64` with `pregnant=true`
- `chronic` → an unspecified condition. Keep it unspecified; don't guess "heart".
- `outdoor_worker` → `outdoor_work=true`

The stateless `/api/status/individual` keeps accepting the old list.

### 5.4 `push_target`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `household_id` or `worker_id` | uuid FK | Exactly one is set |
| `kind` | enum `fcm`, `webpush`, `sms`, `whatsapp` | Voice is out of scope for now |
| `fcm_token` | text | For `fcm` |
| `endpoint`, `p256dh`, `auth` | text | For `webpush` |
| `phone_enc`, `key_id` | bytes, text | AES-GCM with `PHONE_ENC_KEYS`. Decrypted only by `send_queue`. |
| `phone_hmac` | text | HMAC-SHA256(phone, `PHONE_HMAC_KEY`). **Never a plain hash**: 10-digit numbers are easy to brute-force. |
| `verified_via` | enum `otp`, `whatsapp_inbound` | |
| `last_inbound_at` | time, nullable | For WhatsApp's service window |
| `created_at`, `last_ok_at` | time | |
| `fail_count` | int | Disable the target after 5 failures in a row |
| `active` | bool | |

### 5.5 `otp`

| Field | Notes |
|---|---|
| `id`, `phone_hmac`, `purpose` | `purpose` is `household_sms` or `worker_login` |
| `code_hash` | 6-digit code, hashed. Valid for 10 minutes, single use. |
| `attempts` | At most 5, then the code is dead |
| `ip_hash`, `created_at`, `consumed_at` | |

### 5.6 `reading`

As in DETAILS §2.4, plus `period` (`day` or `night`), `used_for_calibration` (bool) and `outlier` (bool). See 7.4 for the rules.

Fields: `id`, `household_id`, `ts` (rounded to the hour), `room` (`bedroom`, `living`, `kitchen`, `other`), `indoor_c`, `outdoor_c` (filled in by the server), `predicted_c`, `source`, `fix_id`.

### 5.7 `feedback`, 5.8 `fix_progress`

As in DETAILS §2.5 and §2.6.
- `feedback` is kept for 90 days and has no free text.
- `fix_progress` is keyed on (`household_id`, `fix_id`).

### 5.9 `notice_log`

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `recipient_key` | **Non-null** text: `h:<household_id>` or `w:<worker_id>` |
| `for_date` | |
| `kind` | `evening`, `morning_work`, `imd_warning`, `worker_brief`, `test` |
| `level` | |
| `channel` | |
| `template_id`, `lang` | |
| `status` | `queued`, `sent`, `failed`, `opened`, `skipped_duplicate` |
| `error` | |
| `queued_at`, `sent_at`, `opened_at` | |

Unique on (`recipient_key`, `for_date`, `kind`, `channel`). NULLs never collide in a unique constraint, which is why `recipient_key` must be non-null.

### 5.10 `org`, `worker`, `worker_session`, `access_log`

- **`org`**: `id`, `name`, `type` (`health_dept`, `ngo`, `rwa`, `school`, `other`), `state`, `district_id`, `created_at`. Created only with a CLI (`python -m app.admin create-org`), never over HTTP.
- **`worker`**: `id`, `org_id`, `role` (`asha`, `anganwadi`, `ngo`, `volunteer`, `org_admin`), `display_name`, `phone_enc`, `key_id`, `phone_hmac`, `district_id`, `active`, `created_at`, `last_seen_at`. The first `org_admin` of each org is invited with the CLI.
- **`worker_session`**: `id`, `worker_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at`, `last_seen_at`.
  - Sessions last 30 days for workers and 12 hours for `org_admin`.
  - Setting `active=false` revokes every session.
- **`access_log`**: `id`, `worker_id`, `household_id`, `action` (`view`, `create`, `edit`, `delete`, `brief`), `at`. Kept for 1 year.

### 5.11 Other tables

- **`forecast_cache`**: only needed without Redis. Keyed by cell and elevation bucket.
- **`imd_warning`**: as in DETAILS §2.10 (`district_id`, `for_date`, `phenomenon`, `color`, `issued_at`, `fetched_at`, `source_url`).
- **`daily_aggregate`**:
  - Built from homes with `share_counts` plus worker-managed homes.
  - Any count below `AGG_MIN_COUNT` is stored as NULL.
  - The API labels these numbers "among Thandak users", because they don't describe the whole population.
- **`consent_event`**: as in DETAILS §2.12. It is kept after deletion and holds nothing else about the household.
- **`job_lock`**: `name` PK, `holder`, `locked_until`.

## 6. API

### 6.1 Conventions

- New endpoints use the `/api/v1` prefix. Existing endpoints stay where they are for the current frontend.
- **Auth** uses `Authorization: Bearer <household token>` or `<worker session token>`. Compare hashes in constant time.
- **Locations:** new endpoints take a location only in a POST body. Existing GET routes with lat/lon stay, but logs never record query strings (8.6).
- **Validation:**
  - Pydantic v2 with `extra="forbid"`, `Literal` enums and finite floats.
  - India bounds: lat 6.5–37.5 and lon 68.0–97.5, and the point must fall inside the district polygons.
  - Invalid input returns 422, never a silent drop.
- **Request limits:** bodies over 16 KB get 413; a POST without JSON gets 415.
- **Errors** look like `{"error": code, "message": short}`, with no stack traces and no echoed input.

### 6.2 Changes to existing endpoints (Phase 1)

| Endpoint | Change |
|---|---|
| All | Validate `lang`, `roof` and `vulnerable` with `Literal`; security headers, limits and logging per section 8 |
| `/api/status/individual` | Guard `start = next(...)` (it raises `StopIteration` today). Accept optional `people[]`, `tenure`, `power_cuts`, `power_cut_hours` and `water_short`. Add `per_person` and `today_actions` in Phase 3. |
| Emergency numbers (everywhere) | Always show 112. Show a state ambulance number only if its row in `data/emergency_numbers.csv` is Verified. Seed Delhi 102 (CATS, https://cats.delhi.gov.in/faqs); everything else goes to `TEAM_TODO`. |
| `/api/weather` | Add `stale` and `provider` |
| `/api/gov/rank`, `/api/wards/list`, `/api/about` | Load the JSON once (`lru_cache`), not on every request |
| Startup | `@app.on_event("startup")` → `lifespan`; verify the `data/MANIFEST.json` checksums |
| `/api/health` | Return `ok`, `time`, `db_ok`, `model_loaded`, `gazetteer_loaded`, `weather_last_ok_at`, `weather_provider`, `imd_last_ok_at` |
| `/api/version` (new) | Return the API version, the rules hash (`verified_numbers`), the catalogue version and the model card date |

### 6.3 Household: saved home (Phase 4)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/v1/households` | `{consent:{version, accepted:true}, lang, place:{lat,lon}, home:{…}, summary:{higher_risk, outdoor_work_window?, share_counts, counts?}, alerts:{enabled, hour_ist, min_level}}` | `{household_id, token}`. The token is shown once. |
| GET | `/api/v1/households/me` | | The saved household. No GPS, because it was never stored. |
| PATCH | `/api/v1/households/me` | Any subset of the POST body | The updated household |
| DELETE | `/api/v1/households/me` | | 204. Deletes everything now and logs `consent_event: deleted`. |
| GET | `/api/v1/households/me/export` | | All stored data as JSON |
| POST | `/api/v1/households/me/token/rotate` | | A new token; the old one stops working |
| POST | `/api/v1/households/me/status` | `{day, people:[Person]}` | Same body as `/api/status/individual`, plus `per_person`, `today_actions`, `calibration`, `imd_warning?` and `fix_progress` |
| POST | `/api/v1/households/me/outlook` | `{days ≤ 7, people:[Person]}` | Per day: `{date, level, reasons, hi_max, tmax, tmin, twb_max, imd_color?, room_peak_range?, persons_at_risk}` |

`status` and `outlook` are POSTs because the people come from the phone.

**Phase 4 prerequisite (frontend team):**
- escape-by-default HTML templating and a CSP on the website
- the household token kept in Keychain/Keystore secure storage in the app

Saved households can't ship until both exist, because a token in a vulnerable page can be stolen.

### 6.4 Readings, feedback, fixes (Phase 6)

These follow DETAILS §3.3 (`POST`/`GET`/`DELETE` `/households/me/readings`, `POST /households/me/feedback`, `PUT /households/me/fixes/{fix_id}`), using the calibration rules in 7.4.

### 6.5 Alert channels

**WhatsApp sign-up, no app needed (Phase 2).** The person messages your number first; that proves the number, so no OTP is needed. The bot then:
1. asks for a PIN code
2. shows the consent notice (`DRAFT` until approved) and asks for "Reply YES"
3. asks for language and alert level

This creates a `household` (`managed_by=self`, cell taken from the PIN's gazetteer location), a `push_target` (`whatsapp`, `verified_via=whatsapp_inbound`) and a `consent_event`.

Commands:
- `STOP`: unsubscribe, and delete the household if it has no other channel
- `HELP`
- `ALERT`: send today's level now
- `PIN`: change the area

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/webhooks/whatsapp` | Verify the provider's signature with `WHATSAPP_WEBHOOK_SECRET`. Reject anything older than 5 minutes. Idempotent on the provider message id. |
| POST | `/api/v1/webhooks/sms-status` | Verify the signature (or the provider's IP allow-list). Idempotent. |
| POST | `/api/v1/push` | `fcm`, `webpush` or `sms`. SMS needs an OTP proof first. WhatsApp is added only through an inbound message. |
| DELETE | `/api/v1/push/{id}` | |
| POST | `/api/v1/push/test` | Maximum 3 per day |
| GET | `/api/v1/vapid-public-key` | |
| POST | `/api/v1/notices/{id}/opened` | Sets `opened_at`. The server never sees `?n=` in a hash route. |

### 6.6 OTP (SMS in Phase 2, workers in Phase 5)

- `POST /api/v1/otp/send {phone, purpose}`:
  - Indian mobile numbers (+91) only.
  - Per phone: 3 per hour and 10 per day.
  - Per IP: 30 per day (kept loose because of CGNAT).
  - When `OTP_DAILY_CAP` is reached, refuse and alert.
- `POST /api/v1/otp/verify {phone, code, purpose}`: at most 5 attempts per code. Returns a short-lived proof (`household_sms`) or a worker session (`worker_login`).

### 6.7 Assisted mode (Phase 5)

- Every worker route checks the worker's org and that the worker manages the household. Every read and write adds an `access_log` row.
- `POST /api/v1/orgs/{org_id}/workers` (`org_admin` of that org only) invites a worker.
- `GET`/`POST`/`PATCH`/`DELETE` `/api/v1/workers/me/households` follow DETAILS §3.6, with persons stored as in 5.3. Consent:
  - `consent:{version, by:"worker", script_version}`: the worker reads out a fixed script in the family's language (`DRAFT` until approved)
  - plus an optional SMS confirmation if the family has a phone
- `PATCH /api/v1/orgs/{org_id}/households/{id} {worker_id}` lets an `org_admin` reassign a household when a worker leaves.
- `GET /api/v1/workers/me/brief?day=&format=json|text`:
  - The text format (for WhatsApp/SMS) holds nicknames, place and actions only. The reasons stay in the app.
  - PDF is out of scope for now.

### 6.8 Government (Phase 6)

`GET /api/v1/gov/today` and `GET /api/v1/gov/trend` follow DETAILS §3.7. They read `daily_aggregate` (NULL below 10) plus the IMD colour, and every response says "among Thandak users".

### 6.9 Internal

- `POST /internal/jobs/{name}` and `GET /internal/metrics` require the `X-Job-Secret` header, compared in constant time.
- Block `/internal/*` at the proxy too.

## 7. Safety logic

### 7.1 Heat level
- Keep the existing weather and IMD logic, after the Phase 0 checks in section 3.
- **IMD district warnings** (Phase 6): our level is never below IMD's.
  - Yellow → at least Moderate
  - Orange → at least High
  - Red → Extreme
  - Reason code: `imd_district_warning`.
- **Headline day:** today before 18:00 IST, tomorrow after.

### 7.2 Per-person rules (Phase 3)

**Fan groups** (all limits from the CSV):

| Person | Fan group |
|---|---|
| `older_*` | `older` |
| has `anticholinergic` | `anticholinergic` (`fan.limit.anticholinergic`) |
| infant, child, pregnant, any condition, other medicines | `older`, with `precautionary:true` |
| otherwise | `adult` |

- The household's fan advice uses the strictest person. For older, infant or chronic people, compare against the upper end of the room range.
- **Wording:** never tell people to turn off their only cooling. With no cooler or AC: "keep skin and clothes wet and use the fan, or move somewhere cooler."
- **AC:** replace "avoid fan alone" with "use the AC" outside power-cut hours. The setpoint number comes from the CSV.
- **Outdoor workers:** use the outdoor heat index and Tmax during their work hours. The work-hour and water numbers come from the CSV.
- **Power cuts:** during cut hours, plan with `fan=False, cooler=False, ac=False`.
- **No per-person level.** `per_person` reports `higher_risk_today` (bool) with reasons, fan state and cards. Only the headline level is shown as a level.

### 7.3 Today actions (Phase 3)

Use the action codes in DETAILS §4.4, with these changes:
- Every number in an action text comes from the forecast or the CSV.
- A cooler is suggested only when 7.5's evaporative rule allows it.
- `infant_care` adds: "Babies under 6 months who only breastfeed don't need extra water, even in heat." The generic "drink water" lines never show for infants.
- `fan_not_safe_for_person` uses the fallback wording from 7.2 when the household has no cooler or AC.

### 7.4 Room estimate
- **Offset fallback** (Phase 1): outside the training range, use outdoor temperature plus the verified roof offset for that hour, with `basis:"offset"` and a wider range. The window plan and fan states keep working.
- **Region:** with `ROOM_MODEL_MODE=validated_only`, numeric estimates show only in Delhi NCT, or for a home with calibration n ≥ 5. Everywhere else, show a sentence instead of numbers.
- **Calibration** (Phase 6) follows the shrinkage method in DETAILS §4.3, with these changes:
  - Clip residuals at ±3 MAD of the home's own residuals before averaging, so one bad reading can't drag the result.
  - Reject a reading only if it is outside 10–55 °C. Once n ≥ 5, flag (don't drop) readings more than 3 MAD from the home's median.
  - Don't use kitchen readings for calibration.
  - Keep separate day and night biases.
  - Apply calibration only once n ≥ 2.
  - Validate before shipping: replay held-out 2016 homes (fit on the first N readings, measure error on later days). Ship only if MAE improves, and record the result in the model card.

### 7.5 Advice content fixes (Phase 1; skip any already in the 31-fix catalogue)
- **Emergency numbers:** as in 6.2.
- **Evaporative advice (coolers and khus screens):**
  - Gate on the afternoon wet-bulb with `evaporative.max_twb` once it's verified.
  - While the only threshold is the `UNVERIFIED` 50% RH, those cards stay off with reason `threshold_not_verified`.
  - Never say "works well" on a day the wet-bulb rule fired.
- **Infants:** the infant water line as in 7.3. **Chronic conditions:** a fluid-restriction line ("ask your doctor how much to drink") and a medicines line ("don't stop them; ask a doctor").
- **Asbestos roofs:** a caution on roof work: don't walk on the sheets; don't scrape, brush, sand or drill them; get trained help.
- **Insulation:** a caution against thermocol false ceilings.
- **Single-home evidence:** the modular roof says "in one measured home", with evidence weight `single_home`.

### 7.6 Alert decision (Phase 2)
- **When to send** an evening alert for tomorrow:
  - tomorrow's level ≥ `alert_min_level`, or
  - tomorrow is at least one level above today and at least Moderate, or
  - IMD shows Orange or Red.
- **Fatigue:** in a run of alert days, send on the first day, on any increase, then every `ALERT_REPEAT_DAYS` days.
- **Morning work alert** at 06:30 when a home's `outdoor_work_window` is hot today.
- **Templates:**
  - Per language. WhatsApp templates must be approved and SMS templates registered on DLT. Hindi SMS is Unicode, so segments are shorter.
  - No health details (ground rule 7).
  - Example shape: "Tomorrow: Extreme heat in {district}. {one action}. Reply HELP".
- **Quiet hours:** nothing is sent between 22:00 and 06:00 IST.
- **Duplicates** are prevented by the `notice_log` unique key.

## 8. Security and privacy

### 8.1 Threat model (each row needs a test in section 10)

| Threat | Controls |
|---|---|
| Scripted abuse burning the weather quota or CPU | Coarse cells, single-flight, daily weather budget, bounded CPU pool, request deadlines |
| Malformed or oversized input | Strict models, bounds, 413/415/422 responses, never a 500 |
| Injection, path traversal, SSRF | Parameterised SQL only; no regex built from user text; static files served from one fixed directory; upstream URLs come from config only |
| Household token theft (XSS, lost phone) | Safe templating + CSP (Phase 4 prerequisite); secure storage in the app; token rotation; delete from the app |
| Worker account takeover or misuse | OTP login, session expiry, revocation on deactivate, org isolation, `access_log` |
| Phone list leak | AES-GCM with a key ring; HMAC (never a plain hash); decryption only in `send_queue` |
| OTP abuse (SMS pumping, brute force) | +91 only, per-phone limits, global daily cap, 5 attempts per code, WhatsApp-first sign-up |
| Webhook spoofing or replay | Signature check, 5-minute window, idempotency on message id |
| Leaks through logs, Sentry or errors | No query strings, tokens, phones, coordinates or bodies anywhere (8.6, 8.8) |
| Tampered safety data or model | `data/MANIFEST.json` checksums verified at startup, read-only `data/`, no pickle |
| Backup leak | Encrypted backups, 14-day retention, restricted access |
| Supply chain | Dependencies pinned with hashes, `pip-audit`, base image pinned by digest |

### 8.2 Tokens
- Tokens are 32 random bytes. Store only SHA-256(token + pepper) and compare in constant time.
- Households can rotate their token. Worker sessions expire and are revoked on deactivation.

### 8.3 Phone numbers
- Phone numbers are encrypted with AES-GCM using a random nonce and a `key_id`, so keys can be rotated.
- Lookups and STOP handling use the HMAC.
- Numbers are never logged and are decrypted only in `send_queue`.

### 8.4 Worker-managed data
- Person fields are encrypted (5.3).
- Every access is logged.
- Tests prove org isolation: a worker can't read another worker's or another org's households.

### 8.5 HTTP hardening
**Headers:**
- website CSP: `default-src 'self'`, plus what MapLibre and the tile host need
- API CSP: `default-src 'none'; frame-ancestors 'none'`
- `nosniff`, `Referrer-Policy: no-referrer`, and a tight `Permissions-Policy`
- HSTS in prod
- no `Server` header

**CORS:** an exact allow-list from `THANDAK_ORIGINS`, no credentials, and `http://localhost` only in dev.

**Other:**
- `TrustedHostMiddleware` with `ALLOWED_HOSTS`.
- Docs routes stay off unless `DOCS_ENABLED=true`.

### 8.6 Logging
- Run uvicorn with `--no-access-log` and log through our own middleware: one JSON line per request with the route template, status, duration and cache result.
- Never log query strings, bodies, tokens, phone numbers or coordinates.
- IPs appear only as a truncated HMAC (`LOG_HASH_SECRET`).

### 8.7 Rate limits

| Scope | Default |
|---|---|
| Authenticated routes | 120/min per token |
| Stateless routes | 300/min per IP. Kept loose because Jio/Airtel CGNAT puts many users behind one IP; tune with metrics. |
| `POST /api/v1/households` | 60/hour per IP, plus a global daily cap |
| OTP | As in 6.6 |
| `/api/v1/push/test` | 3/day |

Every limit returns 429 with `Retry-After`. Use the client IP from `TRUSTED_PROXY_CIDRS` only.

### 8.8 Sentry
- Set `send_default_pii=False`.
- A `before_send` hook strips Authorization headers, cookies, bodies, query strings, and anything shaped like a phone number or token.
- Unit-test the scrubber.

### 8.9 Data integrity
- `data/` is read-only at runtime, and `MANIFEST.json` checksums are verified at startup (prod refuses to start on a mismatch).
- The model loads from XGBoost native JSON/UBJ only.
- Validate upstream payloads (equal-length arrays, IST hours, physical ranges) before caching them.

### 8.10 Container and deploy
- Run as a non-root user with a read-only root filesystem; the database volume is the only writable mount, plus a tmpfs `/tmp`.
- Pin dependencies with hashes, and run `pip-audit` and `bandit` in CI.
- Serve HTTPS only, behind a CDN or WAF.
- Write `docs/DEPLOY.md` in Phase 7.

### 8.11 Backups
- Back up at 02:00 with encryption (`.backup` or `pg_dump`) to object storage, keeping 14 days.
- Test a restore once in Phase 2 and again in Phase 7.
- The consent notice says that deleted data leaves backups within 14 days.

### 8.12 DPDP Act 2023
- **Consent notice** in Hindi and English (`DRAFT` until approved). It covers what is stored, why, for how long, how to delete it, and a grievance contact.
- **Consent** is logged in `consent_event`, and withdrawing is as easy as giving: STOP, or one tap in the app.
- **Export and delete** work in one step.
- **Retention purge** runs as in section 9.
- **Breach response:** a plan in `docs/INCIDENT.md`, covering who decides, who notifies, and the timelines (Phase 7).
- **Children's data** needs parent or guardian consent. Check the DPDP Rules for worker-registered homes and list the result in `TEAM_TODO`.

## 9. Background jobs

All jobs run only in the jobs process, each under a `job_lock`.

| Job | When (IST) | What |
|---|---|---|
| `prefetch_forecasts` | 17:30 and 05:30 | Only the cells of alert-enabled homes. App traffic is cached on demand. |
| `evening_alerts` | Every 15 min, 18:00–21:00 | Decide (7.6) → queue |
| `morning_work_alerts` | 06:30 | |
| `send_queue` | Every minute | Send, retry with backoff, disable a target after 5 failures, respect provider rate limits |
| `retention_purge` | 03:00 | See the list below |
| `backup` | 02:00 | Encrypted; keep 14 days |
| `worker_brief` | 06:30 and 19:00 | Phase 5 |
| `imd_warnings` | 14:30 and 20:30 | Phase 6 |
| `recalibrate` | Nightly, and after each new reading | Phase 6 |
| `daily_aggregates` | 23:30 | Phase 6 |

`retention_purge` does the following:
- hard-deletes soft-deleted rows
- 30 days before a home reaches `RETENTION_DAYS_INACTIVE`, sends "reply YES to keep alerts"; deletes the home if there's no reply
- deletes readings older than 2 years, OTPs older than 1 day, feedback older than 90 days, and access logs older than 1 year

## 10. Tests

Recorded Open-Meteo fixtures go in `tests/fixtures/`: Delhi, Chennai, Jaisalmer, Shimla, and the Delhi heat-wave day of 28 May 2024. Tests never call the internet.

### 10.1 Golden safety cases (Phase 3 STOP shows these with actual outputs)

| # | Case | Expected |
|---|---|---|
| G1 | Plains, 44 °C at 10% RH, normal 38 °C | High |
| G2 | Same day, normal 41 °C | Moderate |
| G3 | Coastal, 36 °C at 75% RH | Extreme |
| G4 | Hill, 32 °C, normal 25 °C, room estimate hidden | Extreme; no exception |
| G5 | 38 °C; tin top floor, elderly person, no devices | Level Moderate (unchanged by the home); `higher_risk_today`; care and go-somewhere-cooler actions |
| G6 | Outdoor worker only | Adult fan limits; level unchanged; work-hours action |
| G7 | Infant | No generic water line; the breastfeeding line is shown |
| G8 | Plains, 47 °C, normal 42 °C | Extreme |
| G9 | 42 °C at 45% RH, cooler at home | Extreme; no "cooler works well" |
| G10 | Anticholinergic medicine | 37 °C fan limit from the CSV |
| G11 | AC, power cut from 14:00 to 16:00 | No AC action during the cut |
| G12 | IMD Orange, our rules say Moderate | High, with reason `imd_district_warning` |

### 10.2 Feature tests

These follow DETAILS §7:
- `test_households.py` (plus token rotation)
- `test_people_rules.py`
- `test_calibration.py` (plus clipping, kitchen exclusion, day/night split)
- `test_offset_fallback.py`
- `test_notify.py`: fatigue rule, quiet hours, no health words in any template or brief text
- `test_worker.py`: isolation across workers and orgs, `access_log` rows, reassignment
- `test_aggregates.py`
- `test_weather_provider.py`: retry, stale fallback, 7 days, provider switch, budget

### 10.3 Security and ops tests
- **Bad requests:**
  - 413 for oversized bodies and 415 for the wrong content type
  - 422 for extra fields, NaN and points outside India
  - hostile strings never cause a 500 and are never echoed back
- **Phone hashing:** `phone_hmac` is not equal to `sha256(phone)`.
- **OTP:** limits, attempts and the global cap work.
- **Webhooks:** unsigned or old webhooks are rejected, and a repeated message id is processed once.
- **Job lock:** two job runners at once → each job runs once.
- **Retention:** WhatsApp-only homes that reply stay; silent ones get the YES prompt, then are deleted.
- **CGNAT:** many tokens from one IP are not blocked at the defaults.
- **Logs and Sentry:** captured logs and Sentry events hold no tokens, phone numbers, coordinates or query strings.
- **Data tampering:** a tampered data file stops a prod startup.
- **Docs:** docs routes return 404 when disabled.
- **Secrets:** no secret-shaped strings in tracked files.

### 10.4 Checks at the end of every phase
- tests
- `ruff`
- `mypy app`
- `bandit -r app`
- `pip-audit`
- `alembic upgrade` followed by `alembic downgrade -1`, both working
- from Phase 7: `scripts/attack_smoke.py` against the running container, plus a load test at peak-evening traffic

## 11. Out of scope
- **Frontend and mobile code.** Each phase report lists the frontend changes needed.
- **Map tiles, borders, the satellite layer and downscaling.**
- **Voice calls and PDF briefs.**
- **Filling in numbers, sources, phone numbers, consent text or templates from memory.**

## 12. Build phases

| Phase | Scope | Stop? | Effort |
|---|---|---|---|
| **0** | Map the repo against this spec. Check section 3. Fill in the commands, create `env.example` and `docs/TEAM_TODO.md`, list conflicts, plan Phase 1. | **STOP** | ½ day |
| **1** | Make the current API solid: 6.2, the weather provider (section 4), offset fallback (7.4), content fixes (7.5), security baseline (8.5–8.7, 8.9), fixtures, CI | | 4 days |
| **2** | Database and Alembic; WhatsApp sign-up and SMS alerts (5.2, 5.4, 5.5, 5.9, 5.11, 6.5, 6.6 for SMS, 7.6); jobs `prefetch_forecasts`, `evening_alerts`, `send_queue`, `retention_purge`, `backup`; Sentry and metrics | **STOP**: dry run with a test group | 5 days |
| **3** | Per-person advice, stateless (7.2, 7.3, `people[]`) | **STOP**: golden cases and safety review | 3 days |
| **4** | Saved households in the app (6.3), FCM and web push, export/delete/rotate. Needs the frontend prerequisite in 6.3. | | 3 days |
| **5** | Assisted mode (5.3, 5.10, 6.6 for workers, 6.7, `worker_brief`) | **STOP**: privacy review | 4–5 days |
| **6** | Learn the home (5.6–5.8, 6.4, 7.4 calibration and its validation); IMD warnings (needs onboarding); government numbers (6.8) | | 4 days + IMD wait |
| **7** | Release hardening: the remaining 10.3 tests, attack script, load test, `DEPLOY.md`, `INCIDENT.md` | **STOP**: launch review | 2–3 days |

Every phase ends with a report of under 300 words, followed by these lists:
- what changed
- test results and the 10.4 checks
- new `TEAM_TODO` items
- Hindi lines for review
- frontend changes needed
- anything not done, and why
