# Load test results

Run 2026-10-25 10:52 against http://localhost:8000: 50 simulated people for 61 s, 40 saved homes, 5 weather cells. 66.6 requests/s. Status codes seen: [200].

| Request | Count | Errors | p50 s | p95 s | p99 s | max s |
|---|---|---|---|---|---|---|
| saved home status | 2527 | 0 | 0.032 | 0.149 | 2.075 | 2.459 |
| one-off status | 932 | 0 | 0.020 | 0.093 | 2.023 | 2.295 |
| light read | 602 | 0 | 0.005 | 0.029 | 0.226 | 2.176 |
| all | 4061 | 0 | 0.024 | 0.132 | 2.049 | 2.459 |

Limits (design choices): no 5xx, errors ≤ 1%, p95 ≤ 1.5 s.
**PASS** (5xx or no answer: 0).
