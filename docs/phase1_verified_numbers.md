# Phase 1: The 5 Critical Numbers, Verified from Original Sources

> **Updated by the gate review:**
> - §2 now has **4 roof groups**. Stone-slab top floor: afternoon −1.8 °C (IQR −2.1 to −1.7), **night +4.5 °C (+4.2 to +5.6)**. RCC/brick top floor: −5.0 / +2.4 °C.
> - The healthy-adult fan limit is disputed above 35 °C. Rule: <35 helps, 35–39 "not enough alone", ≥39 avoid fan alone.
> - See `verified_numbers.csv` (current) and `phase01_gate_review.md`.

Run: 15 Oct 2026. The machine-readable table is `verified_numbers.csv`, the single source of truth for the rules engine.
Every value below was read from the **original paper, official document or primary data**: PubMed/PMC full text, publisher pages, IMD/PIB/NWS/DDMA originals. Anything not confirmed is marked **UNVERIFIED**.

**Citation corrections to the brief:**
- *Jay et al. 2015* is a **JAMA** research letter (Ravanelli, …, Jay; JAMA 313:724).
- *Morris et al. 2019* is in **Annals of Internal Medicine** (171:675).
- *Morris et al. 2021* is in **Lancet Planetary Health** (5:e368).

---

## 1. Fan safety ✅ (with one conflict, resolved by the stricter rule)

| Group | Number | Source | Conditions |
|---|---|---|---|
| Healthy adults 18–40 | Fan helps **below 39.0 °C** air temperature, at any humidity | Morris 2021, *Lancet Planet Health* 5:e368–77, Summary | Modelled; seated at rest, light clothing, pedestal fan 3.5 m/s; 108 cities, 2007–19 |
| Healthy older adults (65+) | Not detrimental **below 38.0 °C** (model) | Morris 2021 | Same |
| Older adults on anticholinergic medicines | **Below 37.0 °C** | Morris 2021 | Same |
| Older adults | **Fans give no meaningful core cooling above 35 °C; advise against** | Meade 2024, *Lancet Planet Health* 8:e256 (review) | Review |
| Older adults (RCT, n=18, age about 72) | **No change** in core, skin or heart-rate load at **36 °C / 45% RH over 8 h** (symptoms slightly better) | O'Connor 2025, *Appl Physiol Nutr Metab* 50:1–12 | Lab, seated |
| Older adults (RCT, n=58, age about 68) | Fan **worsened** core temperature by **+0.3 °C at 45 °C / 15% RH**; slightly helped (−0.1 °C) at 38 °C / 60% RH. **Skin wetting** reduced sweat loss and improved sensation in both. | Chaseling 2025, *JAMA Netw Open* 8:e2523810 | 3-h lab exposures |
| Bedridden older adults, ceiling fan | Peak core temperature −0.2 °C at 31 °C / 45% RH over 8 h; "not wholly efficacious as standalone" | O'Connor 2026, *J Am Geriatr Soc* 74:200 | Lab |

**Directly about Delhi:** Morris 2021 says that *"fan use alone should not have been routinely recommended during hot weather in northern India, Pakistan…"*

**Rule adopted (stricter wins):**
- **Healthy adult:** fan OK below 39 °C.
- **Older or vulnerable person:** *"fan alone is not enough"* **from 35 °C**. *"Avoid fan alone; move somewhere cooler"* **from 38 °C** (37 °C if on anticholinergic medicines).
- **Very hot, dry air (≈45 °C, low RH):** discourage fans for older people; **skin wetting is OK**.

**Skin-wetting limit: UNVERIFIED.** No study gives a separate numeric limit. The blueprint's middle state `fan_with_wet_skin` therefore stays **disabled**, and only qualitative "wet cloth/spray + drink water" advice is shown.

## 2. Indoor vs outdoor by roof type ✅ (Delhi primary data, 2016)

From our own analysis of the CC0 dataset (Phase 0), Delhi, 12 Apr–30 Jun 2016, 56 homes:

| | Afternoon 14–17h: indoor − outdoor, median (IQR) | Night 02–06h |
|---|---|---|
| Tin/metal-sheet top floor (13) | **+1.3 (−0.8 to +2.5) °C** | +3.5 (+2.1 to +4.9) °C |
| RCC/stone-slab top floor (32) | −3.7 (−5.6 to −2.0) °C | +3.2 (+1.9 to +4.9) °C |
| Floor above (11) | −5.3 (−6.7 to −4.4) °C | +2.0 (+1.3 to +3.1) °C |

**Corroborated** by Vellingiri et al. 2020 (Ahmedabad slums, Oct 2017): tin roofs average roughly 2–3 °C hotter indoors than RCC.

**Caveats:** 2016 data (older than 5 years; no newer Delhi data found); small, non-random sample; one outdoor station.

## 3. Cool-roof indoor reduction (Indian field studies) ✅

| Study | Result |
|---|---|
| Arumugam et al. 2013 (AIVC/Cool Roofs conference): unconditioned institutional building, composite climate, Jan–Jun 2012, roof reflectance 0.28→0.57 | Indoor air **−1.07 °C average, −1.38 °C peak** (April); +80 comfort hours |
| Vellingiri et al. 2020, *IJOEM* 24:25: Ahmedabad slum, white reflective paint on tin, 4–10 Oct 2017 | Indoor mean 33.5 vs 34.6 °C, so **about −1 °C** |

- **App value:** **about 1.0–1.4 °C indoor reduction** from a white or reflective roof coating (India).
- **Other options:** ModRoof about −4.5 °C at 1 pm (n=1 home). Thermocol under asbestos is lower than plain asbestos (no number extracted).
- **⚠ Airlite ventilation sheet:** **+3 °C *hotter* than tin, +6 °C vs RCC**, so it is **removed** from the solutions.

**Not used:**
- Kerala anganwadi −1.3 °C: original working paper not reachable (certificate error), so **UNVERIFIED**.
- **Ahmedabad REFLECT trial: results not yet published.**
- Burkina Faso 1.2–1.7 °C: from news coverage of the trial, not a paper.

**Correction made:** earlier project files had labelled "1.2–1.7 °C" as Ahmedabad. **It is the Burkina Faso trial.** Files 05, 08 and 09 are fixed.

## 4. Heat index and wet-bulb danger thresholds ✅

| Item | Value | Source |
|---|---|---|
| **IMD heat wave (plains)** | Tmax ≥40 °C **and** departure 4.5–6.4 °C (heat wave) / >6.4 °C (severe); **or** actual Tmax ≥45 °C (heat wave) / ≥47 °C (severe). Must hold at ≥2 stations for ≥2 consecutive days. | IMD *Definition.pdf* |
| **IMD warm night** | When Tmax ≥40 °C: Tmin departure 4.5–6.4 °C (warm night) / >6.4 °C (very warm night) | IMD *Definition.pdf* |
| **IMD experimental heat index** | Green <35 · Yellow 36–45 · Orange 46–55 · Red >55 °C (NOAA equation) | PIB release 1941012, 20 Jul 2023 |
| **NWS heat index** | Caution 80–90 °F · Extreme caution 90–103 °F · Danger 103–124 °F · Extreme danger ≥125 °F; values are for shade, and sun can add up to 15 °F | weather.gov/ama/heatindex |
| **Wet-bulb danger** | Empirical critical wet-bulb for young healthy adults in humid heat is **30.55 ± 0.98 °C** (lower in dry heat). The theoretical 35 °C limit applies to extended exposure. | Vecellio 2022 *J Appl Physiol* 132:340; Sherwood & Huber 2010 *PNAS* 107:9552 |
| WHO numeric wet-bulb threshold | **None found (UNVERIFIED)** | — |

## 5. Delhi heat-mortality / alert thresholds ✅ (partly)

| Item | Value | Source |
|---|---|---|
| Delhi HAP alert table (source NDMA) | Yellow ≥40 °C · Orange ≥45 °C · Red ≥45 °C *(as printed: Orange and Red share a threshold, likely a typo; **Red cut-off DISPUTED**)* | DDMA Heat Action Plan 2024-25, Table 5 |
| India 10-city heatwave mortality | 2 consecutive days above the **97th city percentile** of daily mean temperature: **+14.7% (95% CI 10.3–19.3)** daily mortality | de Bont 2024, *Environ Int* 184:108461 |
| Delhi heat stress and mortality | "Sweltering" vs "comfortable" India Heat Index days: **+5.9% (4.6–7.2)** all-cause mortality in Delhi | Choudhary 2024, *ES&T* 58:342 |
| Delhi's own 97th-percentile temperature | **UNVERIFIED.** Will be computed from ERA5/IMD 2008–2019 in Phase 2. | — |
| Choudhary IHI class cut-offs for Delhi | **UNVERIFIED** (paper body not accessed) | — |

---

## Gate summary
- **Verified and usable now:** fan rules (stricter-wins), roof offsets (Delhi data), cool-roof effect (about 1.0–1.4 °C), IMD/NWS bands, wet-bulb limits, HAP alert levels (Yellow and Orange), India heatwave-mortality relationship.
- **UNVERIFIED (feature blocked or degraded):**
  - Skin-wetting numeric limit, so the middle fan state is off.
  - Delhi HAP Red cut-off. The app uses IMD's "severe heat wave ≥47 °C" or HAP Orange, whichever is stricter, until DDMA confirms.
  - Delhi 97th-percentile temperature (Phase 2).
  - Kerala anganwadi number.
- **Corrections made to earlier project files:** the Burkina/Ahmedabad mix-up, and Airlite removed.

**STOP: review gate (per blueprint).** Phases 2–8 start after the team approves Phase 0 and Phase 1.
