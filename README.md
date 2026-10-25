# Thandak (ठंडक): heat-risk status and practical fixes

A free, mobile-first heat-safety service for **anywhere in India**, in **Hindi and English**. It tells a family how risky today's heat is, why, and what to do: for each person at home, and for the home itself, using **only evidence-backed numbers**. It works as a website, Android/iOS apps and a **WhatsApp bot** (no app needed). It has three modes: **Individual · Society/RWA · Government**, plus an **assisted mode** for ASHA, anganwadi and NGO workers.

Places are found by GPS, PIN code or place name using an offline gazetteer, so no location is sent to a third-party geocoder. All about 733 districts are ranked for summer heat and vulnerable people. Delhi additionally has ward-level satellite heat maps.

**How the whole app works (structure, diagrams, every flow):** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · visual offline version: [docs/architecture.html](docs/architecture.html) · backend spec: [docs/BACKEND_SPEC.md](docs/BACKEND_SPEC.md)

## What it does

### Heat level and advice
- **Heat level** comes only from the weather forecast and IMD's own rules:
  - the IMD heat-index bands;
  - heatwave limits for plains, hills and coast;
  - "above normal" against each district's 1991–2020 normal;
  - wet-bulb danger.

  IMD's district warning can raise the level, never lower it. Home details never change the level.
- **Advice for each person:**
  - Older people, babies, pregnancy, heart, kidney or diabetes conditions, certain medicines, and outdoor workers each get their own actions.
  - Each person gets a check on whether a fan alone is safe for them.
  - Health details for self-managed homes stay on the phone and are never stored.
- **Room temperature estimate:** an XGBoost model (±1.5 °C, always shown as a range). Its numbers are shown only where they're validated: Delhi, or a home calibrated with its own readings.
- **Home fixes** such as lime whitewash, cool roofs and shading. Every number in them comes from `verified_numbers.csv`, and nothing is typed in by hand.

### Sign-up, login and alerts
- **WhatsApp sign-up:** the family messages the number, sends their PIN code, replies YES to the consent notice, then picks a language and alert level. Replying STOP stops alerts and deletes the home.
- **OTP login** for SMS alerts and for health workers, rate-limited against spam and guessing.
- **Saved homes in the app:**
  - a random token stored only as a hash;
  - export, delete in one step, and change the token;
  - off until the frontend prerequisite is met.
- **Evening alerts** (18:00–21:00 IST):
  - at most one alert per day per channel, never 22:00–06:00, never any health words in the text;
  - channels: WhatsApp, SMS, Android/iOS push (FCM) and Web Push.
- **Master switch** `ALERTS_ENABLED_GLOBAL` (off by default) and a test allow-list.

### Assisted mode (health workers)
- An org and its first admin are created only from the server's command line. Workers sign in by OTP.
- Workers manage families who may have no phone. Each family's consent is recorded with the read-aloud script version.
- At 06:30 and 19:00 each worker gets a brief: homes sorted by risk, with actions for each.
- A worker sees only their own homes, an admin only their own org's. Every access is logged, and person details are encrypted.

### Learning and government view
- **Room readings:**
  - Calibration adjusts the estimate to each home. It was validated on held-out homes before shipping and lowers the error at every number of readings.
  - A one-tap "how was the night?" question.
  - "I did this fix", with the measured effect once there are enough readings.
- **Government numbers:**
  - district totals labelled "among Thandak users";
  - only from homes that chose to share, and any count below 10 is hidden.
- **IMD district warnings:** the adapter is built and stays off until IMD grants API access.

### Privacy and security
- Phone numbers use AES-GCM with key rotation, plus an HMAC for lookups. Logs never hold tokens, phone numbers, coordinates or query strings, and IPs appear only as a hashed tag.
- Strict input checks answer 413, 415 or 422, never a 500. Security headers and CSP are set, and docs routes are off.
- Rate limits are per token for signed-in requests, so families sharing one carrier IP (CGNAT) aren't blocked together.
- Signed webhooks with a 5-minute replay window.
- Data files are checked against `MANIFEST.json`, and production refuses to start if one has been changed.
- Backups are encrypted nightly and kept 14 days; restoring has been tested.
- A hardened container:
  - base images pinned by digest;
  - packages installed with `--require-hashes`;
  - runs as a non-root user with a read-only filesystem.

## What's inside
| Part | Where | Notes |
|---|---|---|
| API, rules and ML serving | `apps/api` (FastAPI) | Public: `/api/status/individual`, `/api/where`, `/api/search`, `/api/area`, `/api/gov/rank`, `/api/weather`, `/api/sources`. Versioned: `/api/v1/…` (households, OTP, webhooks, push, workers, readings, gov) |
| Database and jobs | `apps/api/app`, `apps/api/migrations` | SQLAlchemy + Alembic (SQLite WAL). The jobs process `python -m app.jobs` sends alerts, worker briefs and backups, runs retention, aggregates and recalibration |
| Frontend and mobile apps | `apps/web` (vanilla JS, Vite, Capacitor) | One codebase for the website and the Android/iOS apps |
| Verified numbers | `docs/verified_numbers.csv` (copied to `apps/api/data`) | Every threshold and effect has a source and a status |
| Pipelines and models | `pipelines/`, `ml/` | Gazetteer, district normals (IMD 1° grid), district index; indoor XGBoost (MAE 1.52 °C, leave-home-out) and its calibration check |
| Tests and QA | `tests/`, `docs/qa/` | 183 automated tests (offline, recorded forecasts; 212 with the reference code's tests); QA packs per phase with results |
| Launch docs | `docs/launch/`, `docs/DEPLOY.md`, `docs/INCIDENT.md` | Review gates, pilot plan, draft templates and consent, deploy and incident plans |

## Start the project

You need **Python 3.11** and **Node.js 22** (with npm). No `.env` or keys are needed: the heat check, advice, maps, colony and government pages all work with the built-in defaults.

**First time only** (from the repo root):

Windows (Git Bash):
```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r apps/api/requirements.txt -r apps/api/requirements-dev.txt
cd apps/web && npm ci && npm run build && cd ../..
```
macOS / Linux:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.txt -r apps/api/requirements-dev.txt
cd apps/web && npm ci && npm run build && cd ../..
```
On macOS, XGBoost also needs OpenMP: `brew install libomp`.

**Every time** (keep this terminal open while you use the app):
```bash
cd apps/api
../../.venv/Scripts/python.exe run_local.py "" 8000      # macOS/Linux: ../../.venv/bin/python run_local.py "" 8000
```
Then open **http://localhost:8000**. To stop the server, press Ctrl+C.

**After pulling new code:** run `cd apps/web && npm run build` again (and the `pip install` line if `requirements.txt` changed), then restart the server. If the browser still shows the old site, press Ctrl+Shift+R.

**Changing the frontend:** keep the server running and use `cd apps/web && npm run dev` (http://localhost:5173, reloads on save; `/api` is passed to port 8000).

**Optional:** saved homes, OTP login, alerts and worker mode need secret keys (names in `env.example`). The server reads real environment variables, not a `.env` file. In Git Bash, load one with `set -a; . ./.env; set +a` before starting the server. The jobs process (alerts, backups) runs separately: `cd apps/api && python -m app.jobs`.

## Android and iOS apps (Capacitor)
The apps are the same frontend inside a native shell (`apps/web/android`, `apps/web/ios`). The app needs to reach the API server: it uses the address in `VITE_API_BASE`.

To build the apps, deploy the API over HTTPS ([docs/DEPLOY.md](docs/DEPLOY.md)), put its address in `apps/web/.env.app` (`VITE_API_BASE=https://…`), then run `cd apps/web && npm run android` (Android Studio) or `npm run ios` (Xcode on a Mac).

The API accepts requests from the apps' origins (`capacitor://localhost`, `https://localhost`). Add other web origins with `THANDAK_ORIGINS` (comma-separated).

## Tests and checks
```bash
.venv/Scripts/python.exe -X utf8 -m pytest tests -q        # 183 tests, offline (run `pytest` from the repo root to include the 29 reference tests too)
cd apps/api
ruff check . && mypy app && bandit -q -c pyproject.toml -r app engine main.py && pip-audit -r requirements.txt
alembic upgrade head && alembic downgrade -1
```
- **QA packs** for each phase are in `tests/qa/`, with results in `docs/qa/` (P1–P7 all pass).
- **Against a running server you own:**
  - `python scripts/attack_smoke.py` runs 41 hostile-request checks;
  - `python scripts/peak_load.py` is the evening-peak load test.

## Deploy
See [docs/DEPLOY.md](docs/DEPLOY.md). In short: one image, run as two containers (`api` and `jobs`), with a read-only filesystem and a `/state` volume.
```bash
docker build -t thandak .
docker run --read-only --tmpfs /tmp -v thandak-state:/state --env-file /secure/thandak.env -p 8000:8000 thandak
```

## Before public launch
The backend is built and tested. These are approvals and inputs only the team can supply. Until each one is done, the feature that needs it stays off behind its switch.
- **Messaging:**
  - choose the WhatsApp/SMS provider (its adapter plugs into `app/messaging.py`);
  - DLT registration and template IDs for SMS;
  - WhatsApp Business template approval.
- **Legal:**
  - final consent notice (English/Hindi) and grievance contact;
  - worker read-aloud script;
  - DPDP rules for children's data;
  - legal timelines in `docs/INCIDENT.md`.
- **Reviews:**
  - doctor/public-health review of the advice for each person (`docs/launch/GATE_P3_safety.md`);
  - privacy review (`GATE_P5_privacy.md`);
  - alert dry run (`GATE_P2_dry_run.md`);
  - launch gate (`GATE_P7_launch.md`);
  - native Hindi review.
- **Access and keys:**
  - IMD API access;
  - hosting and backup storage;
  - production secrets;
  - Firebase/APNs and VAPID keys for push.
- **Data:**
  - ambulance numbers for each state (until then the app shows 112);
  - sources for the numbers still marked UNVERIFIED.
- **Frontend:**
  - the saved-homes prerequisite (safe templating, secure token storage);
  - screens for login, alerts, export/delete, readings and the worker app.
- **Pilot:** two weeks with one RWA and one ASHA worker in Jaipur ([docs/launch/PILOT_PLAN.md](docs/launch/PILOT_PLAN.md)).

Everything open is tracked in [docs/TEAM_TODO.md](docs/TEAM_TODO.md).

## Honest limits (also shown on the site)
- **Indoor model:** trained on 56 low/middle-income Delhi homes (2016). Error is about ±1.5 °C, so results are always a range, and numbers are shown only where validated.
- **Ward map:** pre-2022 delimitation (290 units). Roof shares come from Census 2011 (district level).
- **Forecast inputs:** ERA5-Land/Open-Meteo understate urban night heat by about 0.8 °C (validated against a Delhi station).
- **Official data:** IMD warnings are built in, but only switch on once IMD grants API access.
- **Not medical advice:** guidance only. Emergency: 112.

## Licences and attribution
Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0; non-commercial use on the free plan). IMD gridded temperature (district normals), USGS Landsat (public domain), NASA MODIS (public domain), ESA WorldCover (CC BY 4.0), WorldPop (CC BY 4.0), OpenStreetMap (ODbL), DataMeet wards (CC BY-SA 2.5 IN), geoBoundaries (ODbL), S1 indoor dataset (CC0).
