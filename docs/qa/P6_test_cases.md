# Phase 6 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type.
Runner: `python tests/qa/p6_qa.py` against a server with **test** secrets, a throwaway state folder and `HOUSEHOLDS_ENABLED=true` (live forecast).

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P6-01 | A reading gets outdoor air and the model's estimate | A saved home in Jaipur | POST /me/readings `{room: bedroom, indoor_c: 30}` | 201; `outdoor_c` set; `predicted_c` set when the hour is inside the model's range | High | Functional |
| P6-02 | Kitchen readings never calibrate | P6-01 | POST a kitchen reading | `used_for_calibration: false` | High | Functional |
| P6-03 | Impossible readings rejected | — | 9 °C, 56 °C, a time 3 days ago | 422 each | High | Negative |
| P6-04 | List and delete | P6-01 | GET /me/readings; DELETE one | The list shrinks by one; calibration recomputed | Medium | Functional |
| P6-05 | Calibration applies from 2 readings per period | P6-01 | Add readings across several hours | `calibration.applied` once a period has 2 usable readings | High | Functional |
| P6-06 | Room numbers outside Delhi after calibration | Jaipur home | Status before and after ≥ 5 usable readings | `numbers_shown` false, then true when the basis is `model`; stays false on the `offset` fallback (calibration is validated against the model only). The model path is also covered by `tests/test_calibration.py` with an in-range forecast | High | Functional |
| P6-07 | Feedback | — | Two answers for one day; one with an extra `note` | 204, 204 (the second replaces the first), 422 | Medium | Privacy |
| P6-08 | Fix progress | — | PUT /me/fixes/lime_whitewash `done`; an unknown fix | 200 with `measured` (needs 3 days each side); 404 | Medium | Functional |
| P6-09 | Government numbers | Jobs secret | POST /internal/jobs/daily_aggregates; GET /api/v1/gov/today | Job runs; answer says "Among Thandak users"; counts below 10 are null | High | Privacy |
| P6-10 | IMD off until onboarding | — | POST /internal/jobs/imd_warnings | `skipped: IMD_ENABLED is off` | Medium | Functional |
| P6-11 | Calibration validated before shipping | — | Read `apps/api/data/indoor_model_card.json` → `calibration` | `decision` "ship"; MAE lower at every N | High | Safety |
| P6-12 | Automated | — | `tests/test_calibration.py`, `tests/test_aggregates.py` | Pass | High | Functional |
