# Gate after Phase 3: safety review

The 12 golden cases from BACKEND_SPEC §10.1, run through `/api/status/individual` with fixed test forecasts
(`tests/golden_cases.py`; regenerate with `python scripts/golden_report.py`). Generated 2026-10-25 10:58.

**Recommended:** a doctor or public-health person reviews this table, the per-person texts in
`apps/api/data/actions.json` and the fix texts in `apps/api/data/fixes.json`, together with the product owner.

| # | Case | Expected | Our output | Reasons | CSV rows used | Result |
|---|---|---|---|---|---|---|
| G1 | Plains, 44 °C at 10% RH, normal 38 °C | High | level **high** (plains, headline today); fan group adult (avoid from 39 °C); actions: close_windows, open_windows | base_heat_index (41.0), heatwave_departure (44.0) | fan.limit.healthy, heat_index.bands.imd, imd.heatwave | PASS |
| G2 | Same day, normal 41 °C | Moderate | level **moderate** (plains, headline today); fan group adult (avoid from 39 °C); actions: close_windows, open_windows | base_heat_index (41.0) | fan.limit.healthy, heat_index.bands.imd | PASS |
| G3 | Coastal, 36 °C at 75% RH | Extreme | level **extreme** (coastal, headline today); fan group adult (avoid from 39 °C); actions: open_windows | base_heat_index (57.5), wet_bulb_critical (32.2) | fan.limit.healthy, heat_index.bands.imd, wet_bulb.danger | PASS |
| G4 | Hill, 32 °C, normal 25 °C, room estimate hidden | Extreme; no exception | level **extreme** (hill, headline today); fan group adult (avoid from 39 °C); actions: close_windows, open_windows | base_heat_index (32.3), severe_heatwave_departure (32.0) | fan.limit.healthy, heat_index.bands.imd, imd.heatwave | PASS |
| G5 | 38 °C; tin top floor, elderly person, no devices | Moderate (home unchanged); higher_risk_today; care + go-somewhere-cooler | level **moderate** (plains, headline today); fan group older (avoid from 38 °C); actions: open_windows, fan_not_safe_for_person, go_cooler, extra_care; per person: The older person: higher_risk_today=True | base_heat_index (40.6) | fan.limit.older, heat_index.bands.imd | PASS |
| G6 | Outdoor worker only | Adult fan limits; level unchanged; work-hours action | level **high** (plains, headline today); fan group adult (avoid from 39 °C); actions: close_windows, open_windows, fan_not_safe_for_person, work_hours_hot; per person: The outdoor worker: higher_risk_today=True | base_heat_index (51.7) | fan.limit.healthy, heat_index.bands.imd | PASS |
| G7 | Infant | No generic water line; breastfeeding line shown | level **high** (plains, headline today); fan group older (avoid from 38 °C); actions: close_windows, open_windows, fan_not_safe_for_person, infant_care, go_cooler, extra_care; per person: The baby: higher_risk_today=True | base_heat_index (49.4) | fan.limit.older, heat_index.bands.imd | PASS |
| G8 | Plains, 47 °C, normal 42 °C | Extreme | level **extreme** (plains, headline today); fan group adult (avoid from 39 °C); actions: close_windows, open_windows | base_heat_index (43.2), base_air_temp (47.0), severe_heatwave_tmax (47.0) | fan.limit.healthy, heat.band_on_air, heat_index.bands.imd, imd.heatwave | PASS |
| G9 | 42 °C at 45% RH, cooler at home | Extreme; no 'cooler works well' | level **extreme** (plains, headline today); fan group adult (avoid from 39 °C); actions: close_windows | base_heat_index (57.5), wet_bulb_critical (31.6) | fan.limit.healthy, heat_index.bands.imd, wet_bulb.danger | PASS |
| G10 | Anticholinergic medicine | 37 °C fan limit from the CSV | level **moderate** (plains, headline today); fan group anticholinergic (avoid from 37 °C); actions: close_windows, open_windows, fan_not_safe_for_person, medicine_doctor, go_cooler, extra_care; per person: The older person: higher_risk_today=True | base_heat_index (44.8) | fan.limit.anticholinergic, heat_index.bands.imd | PASS |
| G11 | AC, power cut from 14:00 to 16:00 | No AC action during the cut | level **high** (plains, headline today); fan group adult (avoid from 39 °C); actions: close_windows, open_windows, power_cut_hot, use_ac_hours | base_heat_index (49.0), heatwave_departure (43.0) | fan.limit.healthy, heat_index.bands.imd, imd.heatwave | PASS |
| G12 | IMD Orange, our rules say Moderate | High, with reason imd_district_warning | level **high** (plains, headline today); fan group adult (avoid from 39 °C); actions: open_windows | base_heat_index (36.8), imd_district_warning (orange) | fan.limit.healthy, heat_index.bands.imd, imd.district_warning_floor | PASS |

## What the reviewer should look at
- Fan limits per person (older 35/38 °C, anticholinergic 37 °C, others precautionary on the older limits) and that "fan alone not safe"
  never tells a family without a cooler or AC to switch the fan off.
- The infant line (WHO, "not even water"), the medicine and fluid lines ("don't stop them; ask a doctor"), and the "go somewhere cooler" line.
- That household factors never change the level (G5) and that IMD's warning only raises it (G12).
- Open items in `docs/TEAM_TODO.md`: AC setpoint, water interval and warm-night limit have no verified source, so no text uses them.

## Sign-off

| Reviewer | Role | Date | Decision (go / fix first) | Notes |
|---|---|---|---|---|
| | | | | |
