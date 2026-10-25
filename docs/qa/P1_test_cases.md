# Phase 1 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type (the default until the team picks a format).
API requests for most cases are in the Bruno collection `docs/api/bruno/` (environment `local`). Use test values only, never real phone numbers or tokens.

Preconditions for all: API running locally (`cd apps/api && ../../.venv/Scripts/python.exe run_local.py "" 8000`), web app built (`cd apps/web && npm run build`).

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P1-01 | Family result still works | — | In the app: pick Delhi, "Me & my family", tin roof, elderly, fan, finish | Result shows level, reasons, "Your home" line, plan, fixes; no error | High | Functional |
| P1-02 | Heat level unchanged by home answers | — | Run P1-01, then change to RCC roof, no elderly, AC | Level and reasons are the same; only "Your home" changes | High | Functional |
| P1-03 | Outside Delhi: no room numbers | — | Pick Jaipur, finish the questions | Room peak/night numbers are not shown; window and fan rows of the plan still appear | High | Functional |
| P1-04 | Very hot day uses the offset fallback | A forecast above 42 °C (summer, or a test forecast) | Status for Delhi on such a day | `indoor.basis` is `offset`; plan has window advice | Medium | Functional |
| P1-05 | Cooler cards are off | Household with a cooler | Finish the questions | No "cooler" card; the left-out list shows one line "Not shown until its threshold is verified" | High | Functional |
| P1-06 | Only 112 shown by the API | — | Bruno `06_status_individual` | `health.emergency.emergency` = 112, `ambulance` = null (Delhi 102 is not re-checked yet) | High | Functional |
| P1-07 | No prices without a verified source | — | Look at cool-roof, lime and modular-roof fixes | Cost line says to ask for local prices; no ₹ figure | Medium | Functional |
| P1-08 | Numbers in advice are filled in | — | Read the fixes in English and Hindi | No `{n:` text anywhere; numbers such as "1.0–1.4 °C" and "12:00 to 15:00" appear | High | Functional |
| P1-09 | Extra field rejected | — | Bruno `07_status_extra_field_422` | 422, `{"error": "invalid_input", ...}`; the reply doesn't repeat the input | High | Negative |
| P1-10 | NaN and out-of-range values | — | POST status with `"lat": NaN`; GET `/api/weather?lat=50&lon=77` | 422 both | High | Negative |
| P1-11 | Point outside India | — | Bruno `05_outdoor_outside_india_422`; `04_where_outside_india` | Outdoor: 422 `outside_india`; Where: 200 with `in_india: false` (the app shows "outside India") | High | Negative |
| P1-12 | Wrong content type | — | Bruno `08_fix_effect_wrong_type_415` | 415 | Medium | Negative |
| P1-13 | Oversized body | — | POST `/api/fix_effect` with a body over 16 KB | 413 | Medium | Negative |
| P1-14 | Unknown values rejected | — | POST status with `roof: "mansion"`, `lang: "fr"`, `budget: "lots"` | 422 each | Medium | Negative |
| P1-15 | Hostile text | — | `/api/search?q=<script>alert(1)</script>`; status with that string as `roof` | No 500; the string never appears in the reply | High | Security |
| P1-16 | Rate limit | — | Send more than 300 requests to `/api/health` within one minute from one IP | Request 301 gets 429 with `Retry-After` | Medium | Security |
| P1-17 | Security headers | — | Bruno `01_health`; open `/` in a browser and view response headers | API: `default-src 'none'`; site: CSP with `script-src 'self' 'sha256-…'`; `nosniff`, `no-referrer`; no `Server` header | High | Security |
| P1-18 | Site works under the CSP | — | Open the website; browse home, map, colony, government, sources; open DevTools console | Maps and fonts load; no CSP errors in the console | High | Security |
| P1-19 | Docs routes off | `DOCS_ENABLED` unset | Bruno `09_docs_off`; `/openapi.json` | 404 | Medium | Security |
| P1-20 | Tampered data stops prod | Copy of the repo | Change one byte in `apps/api/data/verified_numbers.csv`; start with `ENV=prod` | Server refuses to start, naming the changed file | High | Security |
| P1-21 | Logs hold no coordinates | — | Call `/api/where?lat=28.6139&lon=77.2090`; read the server console | One JSON line with `"route":"/api/where"`; no `28.6139`, no `lat=`, no IP (only a hash, or `-`) | High | Privacy |
| P1-22 | Weather stale flag | Server running, then network off | Load a place, wait past 30 minutes (or restart with a cached cell), cut the network, reload | Reply has `stale: true` and the old data, up to 6 hours | Low | Functional |
| P1-23 | Hindi parity | — | Switch to Hindi; repeat P1-01, P1-05, P1-07 | All new lines appear in Hindi; `fixes.needs_translation` is empty | High | Hindi/English |
| P1-24 | Health and version | — | Bruno `01_health`, `02_version` | Health has `weather_provider`, `model_loaded`, `gazetteer_loaded`; version has `rules_sha256` | Low | Functional |
