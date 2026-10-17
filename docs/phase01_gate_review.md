# Gate Review: Phase 0 + Phase 1 (self-review, 15 Oct 2026)

The team asked: "review your own work, approve, then move ahead."

## Checks run
| # | Check | Result | Action |
|---|---|---|---|
| 1 | **Weather-station timestamp alignment.** Hourly averages: is the stamp the start or end of the hour? | Offsets shift by only **±0.3–0.4 °C** | Uncertainty added to `verified_numbers.csv` |
| 2 | **Was stone-slab correctly grouped with RCC?** | **No.** Stone-slab top floor: afternoon −1.8 °C (RCC −5.0 °C); **night +4.5 °C, the hottest at night**. Stone slab is **23.4% of Delhi households** (Census 2011). | **Fixed: 4 roof groups** (tin, stone slab, RCC/brick, lower floor). File `delhi_indoor_minus_outdoor_by_roof_2016_v2.csv` |
| 3 | **Leave-one-home-out validation** of the rule-based indoor offsets | MAE **1.48 °C** in the afternoon (no-roof baseline 2.47); night 1.53 (baseline 1.65); all hours 1.36 (baseline 1.83) | Roof type clearly helps by day, slightly at night. The app shows **ranges** (IQR), not single numbers. |
| 4 | Fan limit for **healthy** adults: is it disputed? | **Yes.** Morris 2021 (model) says safe below 39 °C; the Meade 2024 review says no meaningful core cooling above 35 °C | Rule: <35 °C fan helps; 35–39 °C "fan alone not enough" (water, wet cloth, cooler place); ≥39 °C avoid fan alone |
| 5 | Is every cool-roof source read in full? | Vellingiri 2020: full text ✔. Arumugam 2013: **conference abstract page only** | Status downgraded to "abstract-level" for Arumugam |
| 6 | Recency (the 5-year rule) | Indoor data 2016 and Census 2011 are both old | Phase 2 searches for newer Delhi indoor data (e.g., the 2024 India indoor-air dataset) before building on 2016 offsets |
| 7 | Logger quality (values >50 °C) | Came from a mislabelled humidity column, now excluded | Logged in decisions.md |

## Verdict: ✅ APPROVED (with the fixes above applied)
Phase 0 (GO WITH LIMITS) and Phase 1 (numbers verified, unverified items flagged) pass the gate. **Moving to Phase 2.**
