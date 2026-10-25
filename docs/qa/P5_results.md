# Phase 5 test results

Run 2026-10-25 11:08 against http://localhost:8002 with test secrets and a throwaway database.

| ID | Title | Result | Notes |
|---|---|---|---|
| P5-01 | Org and first admin only by CLI | PASS | CLI exit codes (0, 0, 0, 0); POST /api/v1/orgs -> 405 |
| P5-02 | Worker sign-in by OTP | PASS | admin session 12.0 h |
| P5-03 | No number probing | PASS | answer {'sent': True, 'expires_in_s': 600}; SMS sent 0; verify 400 |
| P5-04 | Admin invites workers | PASS | [201, 201, 409] |
| P5-05 | Worker adds a home with the consent script | PASS | 201; consent [('given', 'worker')] |
| P5-06 | People encrypted at rest | PASS | clear-text found: [] |
| P5-07 | Worker isolation | PASS | [404, 404]; in B's list: False |
| P5-08 | Org isolation | PASS | 404 |
| P5-09 | Access log | PASS | ['brief', 'create', 'edit', 'view'] |
| P5-10 | Reassignment | PASS | (200, 404, 200) |
| P5-11 | Deactivation revokes sessions | PASS | (200, 401) |
| P5-12 | Brief has no health details | PASS | 'Thandak brief: Today, 0 homes to check.\n'; health words: [] |
| P5-13 | Delete on the family's request | PASS | 204; people left 0; events ['deleted', 'given'] |
| P5-14 | Logs hold no names or numbers | PASS | leaks: 0 |
| P5-15 | Automated isolation tests | PASS | 6 passed, 1 warning in 2.76s |

**15 of 15 passed.**
