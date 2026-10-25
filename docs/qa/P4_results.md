# Phase 4 test results

Run 2026-10-25 15:44 against http://localhost:8000 with test secrets, a throwaway database and HOUSEHOLDS_ENABLED=true.

| ID | Title | Result | Notes |
|---|---|---|---|
| P4-01 | Save a home | PASS | 201; token length 43 |
| P4-02 | No GPS, no token, no people stored | PASS | leaks: 0 |
| P4-03 | Read and edit | PASS | before {'lat': 28.6, 'lon': 77.2}; after {'lat': 26.9, 'lon': 75.8} Jaipur; roof kept tin_top |
| P4-04 | Export | PASS | masked=True; events ['given'] |
| P4-05 | Rotate token | PASS | old 401, new 200 |
| P4-06 | Delete in one step | PASS | 204; left [0, 0]; events ['deleted', 'exported', 'given'] |
| P4-07 | Status with people from the phone | PASS | level low; fan older |
| P4-08 | Outlook | PASS | 7 days: ['low', 'low', 'low', 'low', 'low', 'low', 'low']; days=8 -> 422 |
| P4-09 | Bad requests | PASS | [409, 422, 422, 422, 401] |
| P4-10 | New-home limit (runs last) | PASS | first 429 at create 58 (earlier creates in this run count too) |
| P4-11 | Browser push only to real push services | PASS | evil 422, google 201 |
| P4-12 | Web push key when not set up | PASS | 503 {"error":"not_configured","message":"Web push isn't set up on this server"} |
| P4-13 | Tokens never in logs | PASS | tokens checked: 2 |
| P4-14 | Push crypto and FCM | PASS | 11 passed, 1 warning in 5.31s |

**14 of 14 passed.**
