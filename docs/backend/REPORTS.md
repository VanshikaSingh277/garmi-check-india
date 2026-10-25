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
See the end of this section.

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
