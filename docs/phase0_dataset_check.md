# Phase 0: Go/No-Go Dataset Check (Delhi)

> **Updated by the gate review (`phase01_gate_review.md`):** roof groups are now **4** (stone slab split from RCC). Use `ml/phase0/delhi_indoor_minus_outdoor_by_roof_2016_v2.csv`. The 3-group table below is kept for history.

Run: 15 Oct 2026. Scripts and outputs are in `ml/phase0/`. Raw downloads are kept outside the repo, per the blueprint rule "never raw data".

## Results per candidate source

| # | Source | Delhi units | Roof types (count / share) | Missing values | Year | Access |
|---|---|---|---|---|---|---|
| 1 | **South Asia Indoor Heat dataset** (Tasgaonkar et al., *Scientific Data* 9:285, 2022). Figshare DOI 10.6084/m9.figshare.12546368.v1, **licence CC0** | **59 homes** in the housing sheet. 57 have indoor data; 56 remain after dropping 1 logger placed outdoors. 6 areas: Sarai Kale Khan 12, Lodhi Colony 11, Kasturba Nagar 11, Railway Colony 10, Laxmi Nagar 8, Patparganj slum 7 | Concrete+cement 18 · *floor above (not top floor)* 12 · tin sheet 11 · concrete 6 · stone slabs+cement 6 · stone slab+ext 3 · tin sheet+plastic 2 · bricks+cement 1. **Grouped:** top-floor RCC-type 34, tin/metal 13, not top floor 12 | **Building fields: 0% missing.** Night ventilation 11.9%. Household demographics 34–95% missing (not needed). **Indoor temperature matrix: 25.2% missing overall; 47 of 58 loggers have >50% coverage.** Weather station temperature, humidity, solar radiation and wind: **0% missing** | Indoor: 31 Mar–15 Oct 2016, every 10 min. Station: 12 Apr 2016–14 Feb 2017, hourly. **⚠ 2016 (older than 5 years). No newer Delhi indoor dataset was found.** | Open; downloaded |
| 2 | **Census 2011 HL-02A**, households by predominant roof material, NCT of Delhi (official XLS `DDW-HH0402A-0700.xls`) | **3,340,538 households** (full count), by district and town | Concrete **63.8%** · stone/slate **23.4%** · **GI/metal/asbestos sheets 5.6%** · burnt brick 4.2% · grass/thatch 1.2% · plastic 0.8% · machine tiles 0.6% · hand tiles 0.3% · other 0.1%. Metal-sheet share by district: New Delhi 9.6%, South West 8.6%, South 8.5%, West 5.8%, North West 5.4%, North 4.9%, Central 2.9%, East 2.4%, North East 1.5% | 0% (complete enumeration) | **⚠ 2011 (15 years old)** | Open; downloaded |
| 3 | **NFHS-5** (2019–21), household recode variable `hv215` = main roof material | Delhi sample of about 9,486 households *(figure from a secondary summary, UNVERIFIED)* | Variable exists. **Not tabulated in public summaries we could reach.** | Not checked | 2019–21 (within 5 years ✔) | **Blocked for me:** needs free DHS Program registration. **A team member must register.** |
| 4 | **NSS 76th round** (Jul–Dec 2018), Delhi state-sample report (DES Delhi) | State sample (size not checked) | Roof type was collected (codes: 7 = iron/zinc/metal/asbestos sheet, 8 = cement/RBC/RCC) but **not tabulated** in the report. The report gives "pucca 99.7%", but NSS counts metal and asbestos sheets as *pucca*, so this **can't separate tin from RCC**. Also: independent house 53.9%, flat 38.3%, bad ventilation 8.3% | n/a | 2018 (8 years) | Unit data on the MoSPI microdata portal (login needed) |
| 5 | **Delhi Heat Action Plan 2024-25** (DDMA) | No dataset | None. Contains: alert table (Yellow ≥40 °C, Orange ≥45 °C, Red ≥45 °C *as printed, see Phase 1*); 2019 Landsat hotspot wards (10 named); "about 6 wards highly vulnerable" (index method described, data not released) | n/a | 2024 | PDF only |
| 6 | **Building footprints** (Google Open Buildings v3, Microsoft, OSM, Overture) | **Count: UNMEASURED** (to be done in Phase 2) | **No roof-material attribute** in any of them | n/a | 2023–2026 | Open (CC BY 4.0 / ODbL) |
| 7 | SECC 2011 roof table | — | — | — | 2011 | Site unreachable (DNS failure); skipped. Census 2011 covers the same ground. |
| 8 | Census 2027 houselisting | — | Not released. Delhi houselisting ran about Apr–Jun 2026. Whether it asks about roof material is **UNVERIFIED**. | — | 2026 | Pending |

## The key result we can already use: measured Delhi indoor heat by roof type
From source #1 (summer 2016, 12 Apr–30 Jun; 56 homes; per-home means; °C). Full table: `ml/phase0/delhi_indoor_minus_outdoor_by_roof_2016.csv`.

| Roof group | n homes | Afternoon 14–17h, indoor − outdoor: median (IQR) | Night 02–06h: median (IQR) | Afternoon indoor, 95th percentile |
|---|---|---|---|---|
| Top floor, **tin/metal sheet** | 13 | **+1.3 (−0.8 to +2.5)** | +3.5 (+2.1 to +4.9) | **44.8 °C** |
| Top floor, concrete/stone slab/brick | 32 | −3.7 (−5.6 to −2.0) | +3.2 (+1.9 to +4.9) | 38.4 °C |
| Not top floor (floor above) | 11 | −5.3 (−6.7 to −4.4) | +2.0 (+1.3 to +3.1) | 35.7 °C |

*Outdoor = one weather station (mean 37.8 °C in the afternoon window, 28.4 °C at night).*

**What it shows:**
- In the afternoon, a tin-roof top floor is about **5 °C hotter than an RCC top floor** and about **6.5 °C hotter than a lower floor**.
- At night, **every home type stays 2–3.5 °C hotter than outside**, so night heat is trapped indoors.

## Verdict: **GO WITH LIMITS**

**What we can build now:**
- **Indoor estimate (rule-based, with ranges):** offsets by roof type × floor × time of day from source #1, validated leave-one-home-out. 56 homes is enough for honest *ranges*. It is **too thin for a complex indoor ML model**, so per the prompt we use rules here and say so.
- **Area-level roof prior:** district and town shares of metal-sheet roofs from Census 2011, labelled with their age. Upgrade to NFHS-5 (2019–21) once a team member gets DHS access.
- **The ML core stays where data is abundant:** Model A (Landsat surface heat sharpened to 10 m) and the HVI index, per the blueprint.

**Limits (shown on the site):**
1. The indoor data is from **2016**, small (56 homes), in low/middle-income areas, with no AC. Offsets are shown as ranges and labelled "measured in 56 Delhi homes, 2016".
2. Roof shares are **2011**, flagged until NFHS-5 is added.
3. There is **no per-building roof material** data for Delhi. The user's one-tap roof answer is required; the optional Model C (albedo) comes later.
4. There is **no ward-level vulnerability data** from the Heat Action Plan, so the HVI is built from open layers (Phase 2).

**Team actions (not blocking):**
- (a) **Register free at dhsprogram.com** and request the India NFHS-5 Household Recode (IAHR), so I can tabulate Delhi `hv215` with weights.
- (b) Optional: a MoSPI microdata login for NSS 76 unit data.

**Next:** Phase 1, verifying the 5 critical numbers.
