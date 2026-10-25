# Phase 6 test results

Run 2026-10-25 16:40 against http://localhost:8001 (live forecast, test secrets, throwaway database).

| ID | Title | Result | Notes |
|---|---|---|---|
| P6-01 | A reading gets outdoor air and the model's estimate | PASS | outdoor 32.3; predicted 30.2; period day |
| P6-02 | Kitchen readings never calibrate | PASS | {"room": "kitchen", "used_for_calibration": false} |
| P6-03 | Impossible readings rejected | PASS | [422, 422, 422] |
| P6-04 | List and delete | PASS | 28 -> 27 |
| P6-05 | Calibration applies from 2 readings per period | PASS | {"applied": true, "n_day": 11, "n_night": 9, "bias_day_c": 1.36, "bias_night_c": 0.91, "sd_c": 0.61, "validated": true} |
| P6-06 | Room numbers outside Delhi after calibration | PASS | before False, after False (basis offset, n 20; expected False) |
| P6-07 | Feedback | PASS | [204, 204, 422] |
| P6-08 | Fix progress | PASS | measured: ok; unknown fix 404 |
| P6-09 | Government numbers | PASS | job {'ran': True, 'date': '2026-10-25', 'districts': 0}; rows 0 |
| P6-10 | IMD off until onboarding | PASS | {"ran": true, "skipped": "IMD_ENABLED is off (waiting for IMD onboarding)"} |
| P6-11 | Calibration validated before shipping | PASS | N=2: 1.52->1.313; N=3: 1.52->1.302; N=5: 1.516->1.335; N=7: 1.514->1.347; N=10: 1.51->1.274; N=14: 1.505->1.226 |
| P6-12 | Automated | PASS | 9 passed, 1 warning in 5.62s |

**12 of 12 passed.**
