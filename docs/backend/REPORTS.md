# Phase reports

## Phase 1: make the current API solid (2026-10-25, branch `backend/p1-solid-api`)

The API is now strict about what it accepts and what it shows:
- **Input:** unknown fields, unknown values, NaN and points outside India are rejected (422), never guessed.
- **Limits:** wrong content type (415), over 16 KB (413), over 300 requests a minute per IP (429).
- **Errors:** every error is `{"error", "message"}` and never repeats the input.
- **Headers:** a strict CSP on the API and the website; no `Server` header; docs routes off.
- **Logs:** one JSON line per request with the route template only, no query strings or coordinates.

**Weather** goes through a provider class:
- httpx with a 5 s timeout and 2 retries;
- 0.1° cells, 7 forecast days plus 2 past days;
- one upstream call per cell at a time, data up to 6 h old when Open-Meteo is down;
- a daily call budget.

**Room estimate:** outside the model's training range it uses the measured roof offsets. Outside Delhi the numbers are hidden, but window and fan advice still work. Fan states use the cautious (upper) end of the range.

**Content:**
- Every number inside advice now comes from `verified_numbers.csv`, and only Verified or Computed rows can be shown.
- Unverified prices are gone.
- Cooler and khus cards are off until their wet-bulb threshold is verified.
- Only 112 is shown until a state ambulance number is verified.
- The hill cap on the heatwave rule is removed (the stricter rule).

A data manifest guards the safety files. Prod refuses to start if any file has changed.

### What changed
- New `apps/api/app/`: `config.py`, `http.py` (guard, CSP, rate limit, access log), `manifest.py`.
- `main.py`: strict models (`Person`, `people[]`, `tenure`, power cuts, `water_short` accepted), the India-point check, `lifespan`, `/api/health` fields, `/api/version`, cached JSON, emergency numbers from `data/emergency_numbers.csv`, the 18:00 headline-day switch, `ROOM_MODEL_MODE`.
- `engine/weather.py`: rewritten as above. `engine/indoor.py`: `offset_estimate`. `engine/plan.py`: fan states on the high end. `engine/rules.py`: no cap. `engine/solutions.py`: `{n:…}` numbers, `threshold_not_verified`. `engine/verified.py`: `shown_ok`, `rule_ok`.
- Data: `MANIFEST.json`, `emergency_numbers.csv`, new CSV rows `health.infant.exclusive_bf` (WHO, page read) and `health.avoid_sun_hours`; three rows relabelled `Design choice`.
- FastAPI 0.162 and Starlette 1.10 (pip-audit found 14 vulnerabilities in Starlette 0.41.3).
- Tooling: `requirements-dev.txt`, `apps/api/pyproject.toml`, `.github/workflows/ci.yml`, `.gitattributes` (data bytes identical on every OS).

### Test results and §10.4 checks
- Tests: 106 passed, 0 failed (`pytest tests`; offline, with recorded Open-Meteo fixtures).
- QA pack: 28 of 28 cases passed (`docs/qa/P1_results.md`; API cases by `tests/qa/p1_qa.py`, browser cases by `tests/qa/ui_check.mjs`). P1-04 and P1-22 rely on automated tests, because no day above the model's range or network cut could be produced live.
- ruff: clean · mypy app: clean · bandit: 0 issues · pip-audit: 0 known vulnerabilities.
- alembic: not used yet (no database until Phase 2).
- Note: Starlette warns that its test client will move from `httpx` to `httpx2`; this only affects tests.

### New TEAM_TODO items
Prices with a primary source; per-point height inside hill cells; a source for "even in heat" (infant water line); the model card date.

### Hindi lines for review
Nine new or changed lines, added to `docs/launch/hindi_review.csv` (45 rows in total).

### Frontend changes needed
1. Show 112, plus `health.emergency.ambulance` only when it isn't null. Remove the hard-coded 108 button and 108 in `disclaimer`, `cool_first` and `res_tip_extreme`.
2. When `indoor.numbers_shown` is false, hide room numbers and say why. Handle `note_code` `not_validated_here` and `offset_estimate`. `plan.hours[*].indoor/low/high` can be null.
3. `/api/weather`, `/api/area` and `/api/outdoor` return 422 `outside_india`. Errors are `{"error","message"}`, not `{"detail"}`.
4. Show `stale` or `approximate` weather with its time.
5. `coolroof_cost_inr_per_m2` can be null.
6. Numbers typed into frontend strings (for example "40 °C" in `sx_st`) should come from the API.
7. Use `headline_day` to label the level "today" or "tomorrow".

### Not done, and why
- **Per-point elevation bucket:** Open-Meteo's free elevation API counts every point, so a national 0.1° grid would cost about 32,000 calls. Cells use the cell centre's height instead (TEAM_TODO).
- **Dependencies pinned with hashes, base image by digest:** Phase 7 (§8.10).
- **Async httpx:** the routes are sync and CPU-bound, so the client is sync httpx inside FastAPI's threadpool, with the same timeouts and retries.
- **`/api/where`** still answers `in_india: false` with a 200 for points outside India, so the current app can show its "outside India" message. Every other location endpoint returns 422.

## Phase 2: database, WhatsApp sign-up, SMS alerts, jobs (2026-10-25, uncommitted)

Thandak now has a database: SQLite in WAL mode through SQLAlchemy 2, with Alembic migrations that downgrade.
- **WhatsApp sign-up without the app:** PIN → consent (DRAFT) → language → alert level. STOP, HELP, ALERT, PIN and YES work.
- **SMS:** OTP send/verify with the spec's limits, then SMS push targets.
- **Phones:** encrypted with an AES-GCM key ring and looked up by HMAC. Tokens are stored only as peppered hashes.
- **Alert decision (§7.6):** when to alert, the repeat-day rule, quiet hours, one per day per channel, no health words in any text.
- **Jobs process** (`python -m app.jobs`), every job under a lock: prefetch, evening and morning alerts, send queue (retries, disabling a target after 5 failures), retention purge with the YES prompt, encrypted backup with restore.
- **Ops:** `/internal/jobs/*` and `/internal/metrics` behind `X-Job-Secret`; Sentry with a scrubber.

Nothing reaches a real phone yet: only a fake sender exists, `ALERTS_ENABLED_GLOBAL` is off by default, and `ALERT_TEST_ALLOWLIST` limits a dry run to your own numbers.

### What changed
- New in `apps/api/app/`: `db.py`, `models.py`, `secure.py`, `messaging.py`, `notify.py`, `levels.py`, `jobs.py`, `whatsapp.py`, `api_v1.py`, `backup.py`, `observe.py`.
- New: `alembic.ini`, `migrations/` (0001), `data/message_templates.json` (all DRAFT), `scripts/dry_run_alerts.py`, `docs/launch/GATE_P2_dry_run.md`.
- New packages: SQLAlchemy 2.1.6, Alembic 1.20.1, APScheduler 3.11.3, cryptography 50.0.2, sentry-sdk 2.73.0.

### Test results and §10.4 checks
- Tests: 132 passed, 0 failed.
- QA pack: 19 of 19 (`docs/qa/P2_results.md`).
- ruff, mypy and bandit (0 issues) are clean; pip-audit shows 0 vulnerabilities.
- `alembic upgrade head` → `downgrade -1` → `upgrade head` passes.
- Bugs found and fixed while testing: a wrong OTP code rolled back its own attempt count, so the 5-try limit never applied; Windows database paths broke Alembic's config.

### New TEAM_TODO items
Choose the WhatsApp/SMS provider (the real adapter waits for it); approve the template texts; set the production secrets; set `OTP_DAILY_CAP` (default 500, a guess).

### Hindi lines for review
17 bot and alert templates in `apps/api/data/message_templates.json` (the same texts as `docs/launch/templates/`).

### Frontend changes needed
- POSTs without a body (`/api/v1/push/test`) must send `{}` with `Content-Type: application/json`.
- The app's "Get alerts" screen (Phase 4) uses `/api/v1/otp/*` and `/api/v1/push`.
- Messages link to `/api/v1/notices/{id}/opened`.

### Not done, and why
- **Real WhatsApp/SMS sending:** needs a provider account, DLT registration and approved templates.
- **`forecast_cache` table:** the in-process cache serves one server; the table or Redis is needed only with several servers.
- **Moving backups to object storage:** a deploy step (Phase 7, `DEPLOY.md`).

## Phase 3: per-person advice, stateless (2026-10-25, uncommitted)

`/api/status/individual` now accepts `people[]` (age band, pregnancy, condition and medicine classes, living alone, outdoor work hours, optional nickname). It also still accepts the old `vulnerable` list, mapped as spec §5.3 says, with `chronic` kept as an unspecified condition. Nothing about people is stored or logged.

**Per person:**
- **Fan group:** older; anticholinergic (37 °C, verified); infants, children, pregnancy, conditions and medicines precautionary on the older limits; everyone else adult. Judged on the high end of the room range.
- **Outdoor workers:** their hours are judged on the outdoor heat index and air temperature.
- **No per-person level:** only `higher_risk_today`, with reasons.

**For the home:** fan advice follows the strictest person. With an AC, outside power-cut hours, the advice becomes "run the AC". Without a cooler or AC, it is "keep skin and clothes wet and use the fan, or move somewhere cooler", never "switch the fan off". During power cuts the room is estimated with the fan and cooler off.

**Today actions:** windows, AC hours, power cut in the hottest hours, unsafe fan hours per person, hot work hours (NCDC 12–3 pm from the CSV), checking on someone who lives alone, the infant line (WHO, "not even water"), medicines and fluids ("don't stop them; ask a doctor"), go somewhere cooler, extra care. Every number comes from the forecast or the CSV.

**IMD floor:** a district warning only raises the level: Yellow → Moderate, Orange → High, Red → Extreme. It's ready for Phase 6.

### What changed
New `engine/people.py`, `engine/today.py` and `data/actions.json`; `rules.py` (anticholinergic group, `strictest`, IMD floor); `main.py` (people, nickname, power-cut planning, `per_person`, `today_actions`); new CSV row `imd.district_warning_floor` (Design choice, only raises the level).

### Test results and §10.4 checks
- Tests: 153 passed.
- Golden cases: 12 of 12 (`docs/launch/GATE_P3_safety.md`, with actual outputs).
- QA pack: 11 of 11 (`docs/qa/P3_results.md`).
- ruff, mypy and bandit (0 issues) are clean.

### New TEAM_TODO items
- AC setpoint, drinking-water interval and a warm-night limit: no verified source, so no text uses them (already listed).
- The default work window (06:00–19:00) when an outdoor worker gives no hours: a design choice to confirm.

### Hindi lines for review
All lines in `apps/api/data/actions.json`: roles, medicine classes, fallbacks and 13 actions.

### Frontend changes needed
- A "people at home" step: age band, pregnancy, condition and medicine classes, lives alone, outdoor work hours, optional nickname. Send it as `people[]`, and keep it on the phone.
- Show `today_actions` and `per_person`.
- Optional power-cut hours and AC.

### Not done, and why
- `warm_night` and `imd_warning` actions: there's no verified warm-night limit, and IMD data comes in Phase 6.
- **Gate:** a doctor or public-health reviewer must sign `GATE_P3_safety.md`.

## Phase 4: saved households, app and browser push (2026-10-25, uncommitted)

**Saved homes (spec §6.3)** are built but **off by default** (`HOUSEHOLDS_ENABLED`), because their frontend prerequisite isn't done yet.
- **Routes:** create (the token is shown once), read, edit, export, rotate token, delete in one step, status with people sent from the phone, and an outlook of up to 7 days.
- **Stored per spec §5.1:** the 0.1° cell (never the GPS), home settings, the `higher_risk` flag, and counts only when the family ticks "share". Never people or nicknames.
- **Export** masks phone numbers, because they're decrypted only to send.
- **Delete** leaves only the consent events.
- **Limits:** 60 new homes an hour per IP, plus a daily cap.

**Push:**
- FCM HTTP v1, with an RS256 service-account sign-in and unregistered devices deactivated.
- Web Push, with RFC 8291 encryption (matches the RFC's test vector byte for byte) and RFC 8292 VAPID.
- Browser endpoints must belong to a known push service (no SSRF).
- Evening and morning alerts now also go to app and browser targets. A real sender refuses DRAFT templates, and without keys only the fake sender runs (dev only).

### What changed
New `app/households.py` and `app/push.py`; `main.py` (`/me/status`, `/me/outlook`); `jobs.send_queue` (push channels); `notify.channels`; `api_v1` push validation; `levels.day_level` (IMD colour); settings in `config.py` and `env.example`.

### Test results and §10.4 checks
- Tests: 164 passed.
- QA pack: 14 of 14 (`docs/qa/P4_results.md`).
- ruff, mypy and bandit (0 issues) are clean.
- Bug found and fixed: tests picked up switches from the shell running them; they're now pinned in `tests/conftest.py`.

### New TEAM_TODO items
- Firebase project and service-account JSON; an APNs key for iOS.
- VAPID keys and a contact address.
- The frontend prerequisite (below).

### Hindi lines for review
None new (push texts reuse the message templates).

### Frontend changes needed (prerequisite for switching saved homes on)
- **Website:** escape-by-default templating everywhere user or API text is shown (the CSP is already on).
- **App:** keep the household token in Keychain/Keystore secure storage (for example a Capacitor secure-storage plugin), never in `localStorage`.
- **Then:**
  - the consent screen sends `consent.version` = `CONSENT_VERSION_APP`;
  - sign up with POST `/api/v1/households`, and use `/me/status` and `/me/outlook` with `people[]` from the phone;
  - add "Get alerts on this phone" (FCM token or a Web Push subscription via `/api/v1/vapid-public-key`, then POST `/api/v1/push`);
  - add Export and Delete buttons.

### Not done, and why
- **Switching saved homes on:** waits for the prerequisite above.
- **A live FCM / Web Push send:** needs your keys. The code is tested against the RFC vector and mocked Google endpoints.

## Phase 5: assisted mode (2026-10-25, uncommitted)

ASHA, anganwadi and NGO workers can now manage homes for families who may have no phone.
- **Setup:** orgs and their first admin are created only with the CLI (`python -m app.admin`). The admin signs in by OTP and invites workers.
- **Sign-in:** workers sign in by OTP. The reply is the same for any number, so numbers can't be probed. Sessions last 30 days, 12 hours for admins. Deactivating a worker revokes every session.
- **Isolation:** a worker sees and changes only the homes they manage; anything else is 404. An admin reassigns homes inside their own org only. Every read and write of a home writes an `access_log` row (kept 1 year).
- **Encryption:** people in worker-managed homes are stored with nickname, conditions and medicines encrypted under their own key ring (`PERSON_ENC_KEYS`).
- **Consent:** the worker records the read-aloud script version (DRAFT).
- **Brief:** the list sorts homes by risk with the people at risk and the top actions. The text brief (and the 06:30 / 19:00 `worker_brief` job) holds nicknames, place and actions only. A nickname containing a health word falls back to role names.

### What changed
- New `app/workers.py`, `app/admin.py`, `app/schemas.py` (shared `Person`), and migration `0002` (org, worker, worker_session, access_log, person).
- `api_v1` OTP `worker_login`; `secure.encrypt_field`; the `worker_brief` job; retention purge of access logs and old sessions; the `worker_brief_head` template (DRAFT).

### Test results and §10.4 checks
- Tests: 170 passed.
- QA pack: 15 of 15 (`docs/qa/P5_results.md`).
- ruff, mypy and bandit (0 issues) are clean.
- Alembic 0001 → 0002 upgrade/downgrade passes.

### New TEAM_TODO items
DPDP children's data (already listed); approving the read-aloud script and its version; `PERSON_ENC_KEYS` for production.

### Hindi lines for review
`worker_brief_head` in `apps/api/data/message_templates.json`.

### Frontend changes needed
A worker app or screens: OTP sign-in (`worker_login`), the home list sorted by risk, adding a home with the read-aloud script shown in the family's language, the brief, and admin screens to invite, deactivate and reassign.

### Not done, and why
- **SMS confirmation to the family after a worker adds them (optional in spec §6.7):** it needs an approved template, and a check that the family really owns the number. Left out until the team decides.
- **PDF brief:** out of scope (spec §11).
- **Gate:** `docs/launch/GATE_P5_privacy.md` needs your sign-off.

## Phase 6: learning the home, IMD warnings, government numbers (2026-10-25, uncommitted)

- **Calibration validated before shipping (spec §7.4):** `ml/indoor/validate_calibration.py` replays the 2016 homes held out from training.
  - Out-of-fold MAE is 1.519 °C, matching the model card's 1.52.
  - With a home's own readings, MAE improves by 0.17–0.28 °C at every N from 2 to 14 days (44 homes). Shrinkage is k_day 0.713, k_night 0.636.
  - The decision "ship" is recorded in `indoor_model_card.json["calibration"]`; the code refuses to calibrate without it.
- **Readings:** saved homes can add, list and delete room readings (`/api/v1/households/me/readings`).
  - Each reading gets the outdoor air and the model's estimate for that hour.
  - Readings outside 10–55 °C or older than 2 days get 422.
  - Kitchens never calibrate. Day and night are calibrated separately and need 2 readings per period.
  - One bad reading is clipped; outliers are flagged, not dropped.
- **Room numbers outside Delhi:** shown only for a home calibrated against the model with 5 or more usable readings. On the offset fallback (weather outside the model's range, e.g. October in Jaipur) numbers stay hidden, because calibration was only validated against the model.
- **Feedback and fix progress:**
  - Feedback is one answer per day, with no free text.
  - `PUT /me/fixes/{id}` records planned or done. When there are 3 days of readings each side, it reports the measured change.
- **IMD warnings (spec §7.1):** `app/imd.py` stores district warnings in a normalised format. It stays behind `IMD_ENABLED` (off) until IMD onboarding gives a real feed. The heat level never goes below IMD's colour. Health shows `imd_last_ok_at`.
- **Government numbers (spec §6.8):** the `daily_aggregates` job (23:30) counts only homes that chose to share, plus worker-managed homes. Any count below `AGG_MIN_COUNT` (10) is stored as NULL. `/api/v1/gov/today` and `/gov/trend` always say "Among Thandak users".
- **Jobs:** `imd_warnings` (14:30, 20:30), `daily_aggregates` (23:30), `recalibrate` (01:30). The retention purge now also removes readings after 730 days and feedback after 90.

### What changed
- New: `app/calibrate.py`, `app/learn.py`, `app/imd.py`, `app/gov.py`, migration `0003` (reading, feedback, fix_progress, imd_warning, daily_aggregate, calibration fields on household), `ml/indoor/validate_calibration.py`.
- Changed: `main.py` `_room` applies calibration; `jobs.py`; `config.py` (`IMD_*`, `AGG_MIN_COUNT`); `indoor_model_card.json`; `MANIFEST.json` rebuilt.
- Bruno requests 13–15.

### Test results and §10.4 checks
- Tests: 208 passed (`test_calibration.py`, `test_aggregates.py` added).
- QA pack: 12 of 12 (`docs/qa/P6_results.md`, live forecast). P6-06's expectation was corrected for the offset fallback (see above).
- ruff, mypy and bandit (0 issues) are clean; pip-audit found no known vulnerabilities.
- Alembic base ↔ 0003 upgrade/downgrade passes.

### New TEAM_TODO items
IMD feed access and its district names mapped to ours; confirm `AGG_MIN_COUNT` 10; who may see the government numbers.

### Frontend changes needed
- A "Log a room reading" screen (room, temperature, optional time).
- A one-tap morning question ("How was the night?").
- "Mark this fix done".
- Show the measured change once it exists.

### Not done, and why
- **A real IMD adapter:** IMD's API isn't onboarded (`docs/launch/imd_access_request.md`). Only the normalised file format is read.
- **Access control on `/gov/*`:** counts are aggregated and suppressed below 10, so they are public for now. Decide whether they need a login.

## Phase 7: release hardening (2026-10-25, uncommitted)

- **CGNAT fix (spec §8.7, §10.3):** requests with a token were also counted against the 300/min IP limit, so many homes behind one carrier IP would have been blocked together.
  - Requests with a token now skip the IP limit and keep their 120/min per-token limit.
  - Made-up or expired tokens count against a new per-IP limit (`RATE_BAD_TOKEN_PER_MIN`, 30), so they can't be used to dodge it.
  - The IP limit can now be set with `RATE_STATELESS_PER_MIN`.
- **Deep-nested JSON** now answers 422 like other broken JSON (it was a 400).
- **Attack script** `scripts/attack_smoke.py`: 41 hostile checks, localhost only unless `--i-own-this-host`. Result: 41/41, 0 server errors.
- **Load test** `scripts/peak_load.py` (evening-peak mix): 67 requests/s, 0 errors, p95 0.13 s. p99 is about 2 s and its cause isn't found yet.
- **Supply chain:**
  - `apps/api/requirements.lock` holds all 37 packages with sha256 hashes for Linux/CPython 3.11, built by `scripts/lock_requirements.py`. Every hash was checked by download and the set was audited.
  - The Dockerfile pins both base images by digest and installs with `--require-hashes`, as a non-root user, with code read-only.
  - `.dockerignore` now keeps `.env` files, databases, backups and `.cache` out. CI audits the lock file too.
- **Backup restore** tested again (60 homes, integrity ok).
- **Docs:** `docs/DEPLOY.md`, `docs/INCIDENT.md` (DRAFT), `docs/launch/GATE_P7_launch.md`, `docs/launch/PILOT_PLAN.md` (DRAFT).

### What changed
- Changed: `app/http.py` (token requests skip the IP limit; `BAD_TOKENS`, `blocked()`), `app/api_v1.py` and `app/workers.py` (count bad tokens), `app/config.py`, `main.py` (422 for unparseable bodies), `Dockerfile`, `.dockerignore`, CI, `env.example`.
- New: `tests/test_p7_release.py`, `scripts/attack_smoke.py`, `scripts/peak_load.py`, `scripts/lock_requirements.py`, `apps/api/requirements.lock`.
- Lint fixes in `scripts/golden_report.py`, `tests/qa/p5_qa.py`, `tests/test_aggregates.py`.

### Test results and §10.4 checks
- Tests: 212 passed.
- QA pack: 10 of 10 (`docs/qa/P7_results.md`).
- ruff, mypy and bandit (0 issues) are clean; pip-audit is clean on both requirement files.
- No migration this phase.

### New TEAM_TODO items
Hosting and object storage; INCIDENT.md names, contacts and the legal timelines (TO VERIFY); expected users at launch; the "alerts paused" template; pilot targets; the cause of the p99 delay.

### Frontend changes needed
None new.

### Not done, and why
- **Running the real container:** Docker isn't installed on this machine, so the attack and load runs were against uvicorn directly. Repeat them on staging (gate checklist 1–3).
- **Upload of backups to object storage:** needs a chosen bucket. `DEPLOY.md` §6 gives the host-side sync.
- **Gate:** `docs/launch/GATE_P7_launch.md` needs your sign-off.
