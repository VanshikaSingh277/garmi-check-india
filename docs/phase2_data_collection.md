# Phase 2: Data Collection (the automatic 80%)

Run: 15 Oct 2026. Pipelines are in `pipelines/`. Derived (small) outputs are in `data/derived/`. Raw downloads stay outside the repo.

## What was collected

| Layer | Source | Period | Resolution | Result |
|---|---|---|---|---|
| Hourly weather (temperature, RH, wind, solar) | ERA5-Land via Open-Meteo archive (free, non-commercial, attribution) | Jan 2021 – 13 Oct 2026 | 0.1° grid, 19 points in Delhi | `weather_delhi_daily_city_2021_2026.csv`, `weather_delhi_summer_summary_2021_2026.csv` |
| Heat index + wet-bulb | Our code: NWS Rothfusz; Stull 2011 (`pipelines/common/heat_formulas.py`, tests pass, including the Delhi HAP example 34 °C / 75% → 49 °C) | same | same | in the daily file |
| Live forecast | Open-Meteo forecast API | live | ~1–11 km | Endpoint tested OK |
| Delhi heatwave cut-off (de Bont 2024 definition) | ERA5-Land daily mean, 2008–2019, Safdarjung point | 2008–19 | point | **97th percentile = 35.3 °C** (`delhi_p97_daily_mean.json`) |
| Day surface heat (LST) | Landsat 8/9 C2 L2 via Planetary Computer | Apr–Jun 2021–2026, **84 clear scenes** | 30 m | Delhi median 43.1 °C (p5 38.9, p95 48.3) |
| Night surface heat | MODIS Aqua MYD11A2 LST_Night_1km | Apr–Jun 2021–2026, 45 composites | 1 km | median 23.1 °C (p5 21.3, p95 25.8) |
| Land cover | ESA WorldCover v200 | 2021 | 10 m | tree, shrub, grass, crop, built-up, bare and water fractions per ward |
| Population, under-5, 65+ | WorldPop Global2 R2025A, constrained, UN-adjusted | 2025 | 1 km → area-weighted to wards | Delhi total **2.255 crore** (matches raster sum within 0.1%) |
| Ward polygons | DataMeet Municipal_Spatial_Data (CC BY-SA 2.5 IN) | **pre-2022 delimitation** | 290 units | all of Delhi, 1,488 km² |
| District polygons | geoBoundaries IND ADM2 (LGD, 2021; ODbL) | 2021 | 11 districts | every ward matched to a district |
| Roof-material prior | Census 2011 HL-02A (from Phase 0) | 2011 ⚠ | district | metal-sheet, stone-slab and concrete shares |
| JJ clusters | DUSIB directory summary (2022) | 2022 | district counts | 675 clusters; South East 144, North 109, Central 92 |
| AC/cooler, fan, pucca | NFHS-5 Delhi state report FR374 | 2019–21 | state | **AC or cooler 74.3%** (so about 26% have neither); fan 98.2%; pucca 93.7% |

**Merged output:** `data/derived/delhi_ward_features.csv` and `.geojson`. One row per ward, with:
- day/night LST (mean, p90);
- land-cover fractions;
- population, density, under-5 and 65+ counts;
- district, Census-2011 roof shares, JJ count, AC/cooler share.

## Validation of the weather input
ERA5-Land vs the real Delhi weather station (2016, S1 dataset), with hour-end timestamp alignment:

| Measure | Result |
|---|---|
| Hourly temperature | MAE **1.49 °C**, r = 0.90, bias −0.08 °C |
| Daily maximum | bias **+0.27 °C** |
| Daily minimum | bias **−0.77 °C**: ERA5-Land **under-states urban night heat** |
| Humidity | bias −0.1 pts |

**Spread across Delhi grid points:** only about 0.27 °C. ERA5-Land cannot see neighbourhood differences; the satellite layers are needed for that.

## Problems and gaps (honest)
1. **IMD station data:** not openly downloadable (registration/purchase). We use ERA5-Land plus the Open-Meteo forecast, with the night under-estimate flagged.
2. **CPCB station temperature:** the portal uses a CAPTCHA, which we do not bypass. Not used.
3. **2022 ward boundaries (250 MCD wards):** the OpenCity link has been removed. We use the 290 pre-2022 units (flagged) and the H3 grid for analysis.
4. **JJ cluster locations:** the DUSIB directory has text locations only, no coordinates. Mass geocoding via public Nominatim is not allowed by its policy, so only district counts are used.
5. **Age shares:** WorldPop's under-5 and 65+ *shares* are nearly uniform across Delhi (6.7–7.2%, 5.4–5.7%). They come from district/state proportions, so they add little spatial information. Counts are used; shares are flagged.
6. **Roof prior from 2011:** two newer districts are mapped approximately (Shahdara→East, South East→South). The NFHS-5 household file (2019–21) needs a DHS account (team action).
7. **AC/cooler:** state level only (74.3%).
8. **ERA5-Land extremes:** ERA5-Land understates the very hottest peaks. The city-average 2024 Tmax peak was 45.5 °C, while station records are higher. The status card therefore shows forecast-based levels *plus* IMD warnings, which take precedence.

## Decision
Data is sufficient for:
- **Model A** (surface-heat explanation and sharpening);
- the **HVI**;
- the **rule-based indoor estimate** (Phase 0/1 offsets);
- the **live status** (forecast + heat index + wet-bulb).

**Next: Phase 3 (models).**
