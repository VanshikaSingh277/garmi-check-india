# Phase 0: map and plan

Written 2026-10-24 on `backend/setup` at `39b0d04`. No code was changed in this phase.

The spec was written against `heat-india` at `a4f574e`. That commit isn't in this repo (`garmi-check-india`): the history was rewritten on 2026-10-24 to remove AI attribution lines, so every hash changed. Everything below maps the spec to the current files.

## 1. Map of the repo against the spec

### Layout
| Spec assumes | Repo has |
|---|---|
| Python package `app/` (`mypy app`, `python -m app.jobs`, `python -m app.admin`) | `apps/api/main.py` (all routes) + `apps/api/engine/*.py` (logic). No `app/` package. |
| `data/` with `MANIFEST.json` | `apps/api/data/` (CSV, JSON, GeoJSON, model). No manifest. |
| `tests/` with pytest, recorded fixtures in `tests/fixtures/` | `tests/test_*.py`, plain scripts run one by one (pytest-compatible `test_` functions). No fixtures folder; tests fake the forecast in code. |
| CI | None (no `.github/`). |

### Endpoints
| Endpoint | Spec | State |
|---|---|---|
| `GET /api/health` | add `db_ok`, `model_loaded`, `gazetteer_loaded`, `weather_last_ok_at`, `weather_provider`, `imd_last_ok_at` | returns `ok`, `time` only |
| `GET /api/version` | new | missing |
| `GET /api/weather` | add `stale`, `provider` | has `level` (new), `fetched_at`, `source`; no `stale` |
| `GET /api/where`, `/api/search` | validation + logging rules | lat/lon bounds 6–37.2 / 68–97.6 (spec: 6.5–37.5 / 68.0–97.5 and inside a district polygon) |
| `POST /api/status/individual` | guard `start = next(...)`; optional `people[]`, `tenure`, `power_cuts`, `power_cut_hours`, `water_short` | `start = next(...)` unguarded (`main.py:220`); old `vulnerable` list only; `extra` fields not forbidden; `lang`/`roof` are plain strings |
| `GET /api/area`, `/api/gov/rank`, `/api/outdoor`, `POST /api/fix_effect`, `/api/wards/list`, geojson routes, `/api/about`, `/api/sources` | `lru_cache` for gov/wards/about | `gov_rank.json` and model cards re-read on every request |
| `/api/v1/*`, `/internal/*` | Phases 2–6 | missing (expected) |

### Engine
| Spec item | Where | State |
|---|---|---|
| Heat level, weather only; home factors beside it | `engine/rules.py` `risk()`, `home_factors()` | done |
| Plains/hill/coastal rules, 1991–2020 normals | `engine/normals.py`, `data/district_normals.json` | done; see conflicts C3, C4 |
| Fix catalogue (31 fixes) | `data/fixes.json`, `engine/solutions.py` | done |
| Room model + applicability | `engine/indoor.py` | done; no offset fallback; no `ROOM_MODEL_MODE` |
| Weather provider | `engine/weather.py` | blocking `urllib`, 20 s timeout, no retries; cell = 0.01°; 1 past + 2 forecast days; 30-min in-process cache without size cap or single-flight; no stale fallback; no budget |
| Before/after readings | `POST /api/fix_effect`, `GET /api/outdoor`, `web/src/views/measure.js` | done, device-only |

### Tables
None yet. There is no database (expected: Phase 2).

### Security and ops (spec §8)
| Item | State |
|---|---|
| CORS | exact list, but `http://localhost` allowed in every environment |
| Security headers, `TrustedHostMiddleware`, docs off | none; FastAPI `/docs` and `/openapi.json` are on |
| Logging | uvicorn's default access log, which records query strings with lat/lon |
| Rate limits, body limits (413/415) | none |
| Error shape | FastAPI default (`{"detail": ...}`) |
| Startup | `@app.on_event("startup")` (deprecated); no manifest check |
| Container | runs as root, writable filesystem, unpinned base image, no hashes |

## 2. Spec §3 checks

| Check | Result |
|---|---|
| Severe heat wave maps to Extreme | **Yes on plains and coast.** `rules.risk()` sets Extreme for Tmax ≥ 47 °C (`severe_heatwave_tmax`) and for a departure above 6.4 °C (`severe_heatwave_departure`). Tested in `tests/test_heat_level.py` (`test_47_dry_is_severe_heatwave`, `test_c_shimla_32_hill_heatwave`). **Exception:** where the normal is flagged uncertain (ground ≥ 600 m, `heat.normal_point`), a departure above 6.4 °C gives High, not Extreme. See C3. |
| Heat-index band uses max(air temperature, heat index) | **Yes.** `lvl = base_from_heat_index(max(hi_max, tmax))`, with reason `base_air_temp`. Tested (`test_a_jaipur_44_dry`, `test_dry_air_at_40_plus_never_reads_below_the_air_band`). |

## 3. Conflicts and recommendations

| # | Conflict | Recommendation |
|---|---|---|
| C1 | **Cooler and khus cards use an UNVERIFIED threshold** (`evaporative.max_twb`, 24 °C wet-bulb). Spec §2 rule 3 forbids UNVERIFIED in rules; §7.5 says the cards stay off with reason `threshold_not_verified` until verified. | Follow the spec in Phase 1: both cooler cards and the khus screen go to the left-out list with `threshold_not_verified`. Families lose the cooler card until the team verifies a threshold. |
| C2 | **Room estimate shown outside Delhi** as a labelled rough guide. Spec §7.4: with `ROOM_MODEL_MODE=validated_only` (default), numbers only in Delhi NCT or with calibration n ≥ 5; elsewhere a sentence. | Follow the spec. Outside Delhi, the window plan and fan states switch to the offset fallback (§7.4) and the room numbers become a sentence. |
| C3 | **Cap on uncertain normals** (`heat.normal_point`): on raised ground the departure rule stops at High. Rule 3: a design choice may only make a result more cautious; rule 8: keep the stricter rule. The cap is less cautious. | Remove the cap (stricter). Accept that hill towns with a too-cool normal may show Extreme early. Keep the point normals. |
| C4 | **Station type and point-normal limits are labelled UNVERIFIED** (`heat.station_type`, `heat.normal_point`) but used in a safety rule. Both are cautious (a hill entry of 30 °C and coastal 37 °C fire earlier than plains 40 °C). | Relabel both `Design choice`, which rule 3 allows when it only makes a result more cautious, and keep the TEAM_TODO check against IMD's classification. |
| C5 | **Budget bands UNVERIFIED** (`cost.band_limits_inr`) filter fixes. Not a safety rule, but rule 3 says UNVERIFIED is never used. | Relabel `Design choice`. Budget filtering only moves a fix to the left-out list with a reason; it never hides safety advice. |
| C6 | **Numbers typed into sentences.** Several `fixes.json` texts hard-code numbers (e.g. "12 to 3 pm", "2–4.5 °C", "1.9–2.4 °C", "6 months", "40 °C" in `sx_st`). Rule 2 needs every such number from the CSV. | Phase 1: audit every user-facing string for digits; move each into a CSV row with a source and fill the text from it. List anything without a source in TEAM_TODO. |
| C7 | **Ambulance number 108 shown everywhere.** Spec §6.2: always 112; a state number only if its row in `data/emergency_numbers.csv` is Verified. | Phase 1: show 112 everywhere; show Delhi 102 only after the team re-checks it; drop 108 until a state's row is verified. |
| C8 | **Headline day.** Spec §7.1: today before 18:00 IST, tomorrow after. The app uses the next 24 h, counting a day only when its afternoon is ahead. | Close in effect. Phase 1: make the cut-off explicit at 18:00 and label the day in the response. |
| C9 | **Asbestos caution** lacks "drill" (spec §7.5). | Add it in Phase 1 (English and Hindi). |
| C10 | **Package layout** (`app/` vs `apps/api/`). | New backend code goes in `apps/api/app/` (db, jobs, notify, security), so `python -m app.jobs` and `mypy app` work when run from `apps/api/`. `engine/` stays. |
| C11 | **Data location.** Spec says the database never goes in `data/` and `data/` is read-only with a manifest. | Phase 1: add `apps/api/data/MANIFEST.json` (SHA-256 of each file); the database path comes from `DATABASE_URL`, outside `apps/api/`. The point-normals cache moves out of `apps/api/.cache/` to the same writable volume. |
| C12 | **Tests are plain scripts.** | Add pytest (dev only); the existing files run unchanged under it. |

## 4. Phase 1 plan

**Branch:** `backend/p1-solid-api`, from `backend/setup` once merged.

**Order of work**
1. Tooling and CI: pytest, ruff, mypy, bandit, pip-audit; a GitHub Actions workflow that runs them; `requirements-dev.txt`.
2. Input rules (§6.1): Pydantic `extra="forbid"`, `Literal` enums, finite floats, India bounds + district check, 413/415/422, error shape; guard `start = next(...)`.
3. HTTP hardening (§8.5–8.7): security headers, CORS per `ENV`, `TrustedHostMiddleware`, docs off unless `DOCS_ENABLED`, JSON request log without query strings, in-process rate limiter.
4. Weather provider (§4): `WeatherProvider` + `OpenMeteoProvider` on async httpx (5 s, 2 retries), 0.1° cells + 100 m elevation bucket, 7 + 2 days, single-flight, 6-hour stale fallback with `stale=true`, `WEATHER_DAILY_BUDGET`; recorded fixtures (Delhi, Chennai, Jaisalmer, Shimla, Delhi 28 May 2024).
5. Room estimate (§7.4): offset fallback and `ROOM_MODEL_MODE`.
6. Content fixes (§7.5) and conflicts C1, C3–C9.
7. Endpoint changes (§6.2): `/api/health` fields, `/api/version`, `lifespan`, `lru_cache`, `MANIFEST.json` check.

**Risks**
- Coarser cells (0.01° → 0.1°) change forecasts slightly in hilly places; the elevation parameter limits this.
- C1 and C2 remove advice users see today (cooler cards; room numbers outside Delhi).
- Recording fixtures needs one-time live calls (about 10 archive/forecast calls).
- Old app builds still call `/api/status/individual` with the old body; `extra="forbid"` must not break them (fields stay accepted).

**New dependencies (each needs your OK)**
| Package | Use | Runtime or dev |
|---|---|---|
| `httpx` | async weather client (§4) | runtime |
| `pytest` | test runner | dev |
| `ruff`, `mypy`, `bandit`, `pip-audit` | spec §10.4 checks | dev |

Phase 2 will add `SQLAlchemy`, `alembic`, `APScheduler`, `cryptography` and `sentry-sdk`; they'll be asked for then.
