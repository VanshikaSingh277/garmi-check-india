# Garmi Check India: heat-risk status and practical fixes

A mobile-first website that tells anyone **anywhere in India** their **current heat-risk status** and gives **only evidence-backed, implementable solutions**, in **Hindi and English**. It has three modes: **Individual · Society/RWA · Government**. Places are found by GPS, PIN code or place name using an offline gazetteer, so no location is sent to a third-party geocoder. All about 733 districts are ranked for summer heat and vulnerable people. Delhi additionally has ward-level satellite heat maps.

**How the whole app works (structure, diagrams, every flow):** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · visual offline version: [docs/architecture.html](docs/architecture.html)

## What's inside
| Part | Where | Notes |
|---|---|---|
| API + rules + ML serving | `apps/api` (FastAPI) | `/api/status/individual`, `/api/where`, `/api/search`, `/api/area`, `/api/gov/rank?scope=india|delhi`, `/api/weather`, `/api/sources`, `/api/india/districts.geojson`, `/api/wards.geojson` |
| Frontend | `apps/web` (vanilla JS, 14 KB gzipped) | MapLibre loads lazily, only for map views |
| Verified numbers (single source of truth) | `docs/verified_numbers.csv` (copied to `apps/api/data`) | Every threshold/effect has a source and status |
| Pipelines | `pipelines/` | `places/build_gazetteer.py` (GeoNames → offline India gazetteer), `india/district_layer.py` (ERA5 summers + WorldPop → all-India district index), weather, Landsat/MODIS/WorldCover (Planetary Computer), Delhi ward table |
| Models | `ml/` | Indoor XGBoost (MAE 1.52 °C, leave-home-out), Model A LightGBM (spatial-CV MAE 0.90 °C, R² 0.82), HVI |
| Docs | `docs/` | Phase reports 0–3 and 8, decisions, sources |
| Tests | `tests/` | Table-driven safety tests (fan advice, risk levels) + formula tests |

## Run locally
```bash
cd apps/api
python3 -m pip install -r requirements.txt
python3 run_local.py "" 8000
```
Then open http://localhost:8000.

On macOS, XGBoost needs OpenMP (`brew install libomp`). Linux/Docker installs `libgomp1` automatically.

## Run the tests
```bash
python3 tests/test_heat_formulas.py
python3 tests/test_rules.py
PYTHONPATH=tests python3 tests/test_india.py
```

## Deploy (one container)
```bash
docker build -t garmi-check .
docker run -p 8000:8000 garmi-check
```
Any container host works (Render / Railway / Fly.io / an India-region VM). Point it at the Dockerfile; it serves on `$PORT`.

## Rebuild data and models (optional, about 1 hour)
1. `pipelines/weather/fetch_history.py` → `process_history.py`
2. `pipelines/satellite/landsat_lst_composite.py`, `modis_night_and_worldcover.py`, `landsat_sr_indices.py`
3. `pipelines/vulnerability/ward_table.py` → `add_district_priors.py`
4. `ml/indoor/compare_indoor_models.py` → `tune_train_indoor.py`; `ml/model_a/train_model_a.py`; `ml/hvi/build_hvi.py`
5. `scripts/build_site_data.py` copies the outputs into `apps/api/data`.

## Honest limits (also shown on the site)
- **Indoor model:** trained on 56 low/middle-income Delhi homes (2016). Error about ±1.5 °C, so results are always shown as a range.
- **Ward map:** pre-2022 delimitation (290 units). Roof shares come from Census 2011 (district level). JJ clusters are district counts.
- **Forecast inputs:** ERA5-Land/Open-Meteo understate urban night heat by about 0.8 °C (validated against a Delhi station).
- **Missing official data:** no IMD warnings API or CPCB station feed is integrated (not openly accessible).
- **Not medical advice:** guidance only. Emergency: 108 / 112.

## Licences and attribution
Open-Meteo (non-commercial use, attribution), USGS Landsat (public domain), NASA MODIS (public domain), ESA WorldCover (CC BY 4.0), WorldPop (CC BY 4.0), OpenStreetMap (ODbL), DataMeet wards (CC BY-SA 2.5 IN), geoBoundaries (ODbL), S1 indoor dataset (CC0).
