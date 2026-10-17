# Phase 3: Models

Run: 15 Oct 2026. Code is in `ml/`. Model cards: `ml/indoor/indoor_model_card.json`, `ml/model_a/model_a_card.json`.

## M-I. Indoor temperature (home level): ML beats the rules → **XGBoost**
- **Data:** 56 Delhi homes, hourly, 12 Apr–30 Jun 2016 (S1, CC0).
- **Inputs:** ERA5-Land/ERA5 weather (same type as the live forecast) + the user's taps (roof group, fan, cooler).
- **Validation:** GroupKFold by home (the test home is never seen in training).

| Model | MAE (all) | RMSE | MAE 14–17h | MAE 02–06h | Train time |
|---|---|---|---|---|---|
| Rule (outdoor + roof×hour offset) | 2.11 | 2.65 | 2.17 | 2.31 | 0.3 s |
| Linear regression | 1.71 | 2.20 | 1.99 | 1.77 | 0.1 s |
| Ridge | 1.71 | 2.20 | 2.00 | 1.76 | 0.04 s |
| Random Forest | 1.65 | 2.23 | 1.99 | 1.57 | 27 s |
| LightGBM | 1.52 | 2.00 | 1.76 | 1.53 | 3.5 s |
| **XGBoost** | **1.51** | **1.99** | 1.76 | 1.53 | 1.8 s |

(The station-input run shows the same ranking: `ml/indoor/indoor_model_comparison.csv`.)

**Why XGBoost:** it had the lowest error and was faster to train than LightGBM here. SHAP explains it.
- **Tuned:** max_depth 6, lr 0.06, 600 trees, min_child_weight 20. CV MAE **1.52 °C** (afternoon 1.67, night 1.63).
- **80% band shown to users:** prediction −2.2 / +2.7 °C.
- **SHAP (makes physical sense):**
  - tin roof **+2.7 °C at 15:00** (+0.5 at 03:00);
  - floor above **−2.0 °C at 15:00**;
  - stone slab +0.5 / +0.6 °C;
  - the previous 2–24 hours' heat and having a cooler are the strongest drivers.

**This revises the Phase 0 decision** ("rules, not ML"). Hour-by-hour, a fixed offset can't follow how a house heats up and cools down, but lagged-weather ML can. Logged in decisions.md.

**Limits:**
- 2016 data; low/middle-income homes with no AC; 56 homes.
- "Cooler" means the home *has* one (usage wasn't logged).
- Indoor *air* only (no radiant heat).

## M-A. Surface heat drivers (area level): **LightGBM**
- **Target:** Landsat pre-monsoon LST (84 scenes, 2021–26), 90 m, 183,691 cells.
- **Features:** NDVI, NDBI, MNDWI, albedo, WorldCover fractions, DEM, distance to water. No latitude/longitude.
- **Validation:** spatial-block (5 km) GroupKFold.

| Model | MAE | RMSE | R² | Train time |
|---|---|---|---|---|
| Linear regression | 1.05 | 1.35 | 0.76 | 0.07 s |
| Random Forest | 0.905 | 1.19 | 0.815 | 30 s |
| **LightGBM** | **0.903** | **1.19** | **0.816** | 6 s |
| XGBoost | 0.905 | 1.19 | 0.815 | 2.9 s |
| HistGradientBoosting | 0.908 | 1.19 | 0.814 | 24 s |

- **Tuned LightGBM:** 400 trees, lr 0.03, 63 leaves, spatial-CV MAE **0.903 °C**.
- **SHAP importance:** NDBI 1.23 > elevation 0.62 > tree fraction 0.25 > MNDWI 0.22 > albedo 0.20 > built 0.19 > NDVI 0.14.
- **SHAP signs:** NDVI −, tree −, water −, built +, NDBI +, bare + ✔.
- **Caveats:**
  - Albedo comes out "+" (bright dry soil is hot in pre-monsoon Delhi), so **Model A must not be used to estimate cool-roof effects**. Fix effects come only from verified numbers (blueprint rule confirmed).
  - Elevation "−" is confounded with the forested Ridge.
- **Per-ward top-3 heat drivers:** `ml/model_a/ward_top3_heat_drivers.csv`, used for the "why is this area hot" text.

## M-B. Heat Vulnerability Index (scored, not trained: no heat-illness labels exist)
- **Formula:** HVI = E + S − A, equal weights, min-max scaled. `ml/hvi/delhi_ward_hvi.csv`
- **Check 1, weights:** PCA weighting vs equal weights, Spearman **0.63**. The ranking is moderately weight-sensitive because PCA leans on district-level roof/JJ data. Equal weights are kept (blueprint default) and the sensitivity is disclosed.
- **Check 2, external:** 5 of the 9 Delhi HAP 2019 hotspot wards are found in our file. They sit at the **73rd percentile** of our day surface heat (Harkesh Nagar at the 82nd).
- **Top wards:** the Walled City (Ballimaran, Kucha Pandit, Bazar Sitaram, Jama Masjid, Turkman Gate).
- **District mean HVI:** Central 0.74 … South 0.32.

## Risk level: rules (data too thin for ML)
There are no labelled heat-illness outcomes per home or ward, so a risk-level classifier **cannot honestly be trained**. The level uses the blueprint's rule table plus the verified thresholds:
- IMD heat-index bands;
- Vecellio wet-bulb;
- IMD heat-wave criterion and the Delhi p97 of 35.3 °C;
- the roof, vulnerable-person and no-cooling raises.

## Next
Phase 4–7: build the site (3–5 taps, three modes, solutions, Hindi/English).
