# Phase 3 test results

Run 2026-10-25 11:07 against http://localhost:8000 (live forecast).

| ID | Title | Result | Notes |
|---|---|---|---|
| P3-01 | Old form still works | PASS | [['older'], ['child']] |
| P3-02 | People list accepted | PASS | 2 people; fan group older |
| P3-03 | Level unchanged by people | PASS | low / low |
| P3-04 | No per-person level | PASS | {"higher_risk_today": false, "reasons": ["older"]} |
| P3-05 | Nickname echoed, never logged | PASS | label=Dadiqa; in server log=False |
| P3-06 | Unsafe nickname rejected | PASS | 422 {"error":"invalid_input","message":"Check these fields: people.0.nickname"} |
| P3-07 | Unknown person fields rejected | PASS | [422, 422, 422, 422] |
| P3-08 | Hindi actions | PASS | 1 actions (level low); all Hindi=True; placeholders left=False |
| P3-09 | Power cut and AC inputs | PASS | AC hours inside the cut=False; bad time -> 422 |
| P3-10 | Golden cases G1-G12 | PASS | 12 passed in 5.50s |
| P3-11 | Per-person rules | PASS | 9 passed in 5.31s |

**11 of 11 passed.**
