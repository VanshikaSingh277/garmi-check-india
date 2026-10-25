# Task: Rework Thandak's fix recommendations to be personal and real-time

## Context

Thandak is our free, bilingual (English and Hindi) heat app for India. The backend is FastAPI on Python 3.11, the frontend is vanilla JS built with Vite, and Capacitor wraps it for Android and iOS. A family answers a few questions (roof type, vulnerable people, cooling devices). The app then shows today's heat level, a 24-hour plan, a room temperature range and fixes sorted by cost. Safety advice comes only from published rules, and every number lives in `verified_numbers.csv` with its source and status.

We built a new fix engine outside the repo. A review found it personalised by satellite area data instead of by the home and today's weather. The reworked reference is in `reference/thandak_v2/`:

- `thandak_recommend.py` is the reference engine (standard library only).
- `thandak_rules.json` holds 29 fixes with triggers, conditions and English/Hindi labels.
- `test_thandak_recommend.py` has 29 tests that define the expected behaviour.

Treat these files as the spec. Port the behaviour into the existing code. Don't add a second engine or a second fix catalogue.

## Goal

Family advice is driven by the household's answers and today's forecast, it works anywhere in India with no satellite data, and every questionnaire answer changes what the family sees.

## Step 1: map the code, then stop

List the file and function for each of these:

- the current fix catalogue and filter
- the `verified_numbers.csv` loader
- the heat-level rules
- the hourly plan and the fan-limit logic
- the room model's roof mapping
- `/api/status/individual`
- the questionnaire UI
- the i18n files and the bilingual key-sync test

Then give me a short plan: which reference pieces go where, and any conflicts between the reference and the current code. Stop and wait for my OK before editing anything.

## Requirements

1. **One catalogue.** Merge the reference fixes into the existing catalogue and keep its "left out because" behaviour. Every effect number, the 50% evaporative humidity limit and the cost-band rupee limits go through `verified_numbers.csv` with source and status. Nothing unverified is shown as a fact. Where the reference and the current code disagree on a safety rule, the current code wins; tell me about it.

2. **Family triggers.** Household answers and today's heat level trigger family fixes. Satellite area causes only boost ranking and add a "because" line; they never trigger or block a family fix. A place with no satellite profile, or an area cooler than the city average, still gets full family advice.

3. **Today section (real-time).**
   - Add a "Today" tier with these actions: window timing (always shown), care for vulnerable people, fan limits, cooler advice, night fan pull, and outdoor work. Order them safety, then core, then advice.
   - Take the heat level from the existing heat-level rules. Don't reimplement them.
   - Afternoon humidity is the mean forecast RH (`relative_humidity_2m`, already fetched) over the next 12:00–16:59 window. Use `afternoon_rh` for this, and compute `now` in Asia/Kolkata, not server time.
   - If humidity is unknown, leave evaporative fixes out with the reason "humidity unknown".

4. **Questionnaire.**
   - Add four questions: asbestos roof as a roof option, cross-ventilation (yes/no), someone works outdoors (yes/no), and budget.
   - Map the existing roof answers to the rules enum: stone slab → `stone_slab`, concrete or brick → `concrete`, floor above → `top_floor: false`.
   - The room model has no asbestos category. Hide the room estimate for asbestos roofs unless the training data supports a mapping, and ask me before choosing one.

5. **Vulnerable people change the content.** `vulnerable: true` adds the care fix and passes `fan_profile: "vulnerable"` to the existing fan-limit logic, so the hourly plan uses the stricter limits. Don't implement this as a score boost.

6. **Ranking.**
   - The Today tier is ordered safety, core, advice.
   - In the other tiers, fixes with a measured or programme-reported number come first, then the rest.
   - Numbers from global reviews (such as dense trees, "0–9 °C") are not shown as a range.
   - Show at most 6 fixes in Today and 3 in each other tier.

7. **Left-out fixes.** Return them with a reason:
   - over budget, where roof fixes flagged `subsidy_possible` add "check cool-roof subsidies or NGO programmes"
   - too humid
   - humidity unknown
   - wrong climate

   Don't list the other variant of a pair that is shown (cooler dry vs. cooler humid).

8. **Hindi.**
   - No English appears in Hindi mode: titles, steps, cautions, effect text and reasons are all in Hindi.
   - Add the missing `*_hi` fields (`validate_rules` lists them). Write them in everyday spoken Hindi, not line-by-line translation, and list every new Hindi line for native review.
   - Extend the existing key-sync test to cover the rules file.
   - Anything that still falls back to English appears in `needs_translation`.

9. **Input safety.** Unexpected values ("Low", rupee amounts, an unknown roof, "HIGH") are normalised, or ignored with a warning. They never crash the endpoint or remove safety fixes.

10. **Before/after readings.**
    - A family can log one indoor reading per day at a fixed time, before and after a fix.
    - Pair each reading with the outdoor temperature for that hour from forecast data already cached for that grid cell. No new third-party calls.
    - Compute the effect with `estimate_fix_effect`: it uses the indoor-minus-outdoor gap, needs at least 3 days on each side, and its range is never narrower than ±0.5 °C. Show the result as "measured in your home".
    - Store readings on the device by default and upload only with explicit opt-in.

11. **API and UI.**
    - Extend `/api/status/individual` (or the existing fixes endpoint) with `today`, `quick`, `moderate`, `long`, `excluded`, `fan_profile`, `warnings` and `needs_translation`.
    - In the frontend, add a "Today" card above the fix list, and show left-out fixes in the existing UI.
    - Load the new UI code on demand so the first load stays near 35 KB gzipped.

## Out of scope

- the satellite layer, 100 m profiles and the SHAP pipeline
- real-time downscaling
- heat-level thresholds
- room model retraining
- Open-Meteo and map tile changes
- colony and government screens beyond what the new response shape needs
- new dependencies

## Working style

- Keep updates short: one or two lines when a requirement lands, plus anything that blocks you. No running commentary.
- If you change approach, say so in one line with the reason.
- Use at most two subagents, for read-only exploration only.
- Run the tests for each requirement when you finish it, and the full suite once at the end. Don't re-run passing tests to double-check.
- Commit once per requirement with a clear message.
- Keep code and files free of planning notes. Open questions go in the final report.
- Ask before deleting or renaming existing catalogue entries or i18n keys.

## Done when

- The reference tests are ported into our suite and pass against the real catalogue.
- All existing tests pass, including the bilingual key-sync test, which now covers the rules.
- API tests cover three scenarios:
  - a Jaipur family with a tin roof, top floor, an elderly parent, a fan and a cooler, on a High day
  - a village with no satellite profile
  - a humid city with a cooler at 75% afternoon humidity
- `validate_rules` reports zero errors.

## Final report

Keep it under 250 words. List what changed, by requirement, and the test counts. Then give three lists:

- Hindi lines for native review
- sources still to link
- numbers still to verify (cost bands, the 50% humidity limit)

Put any questions last.
