# Phase 7 test results

Run 2026-10-25 16:41: attack against http://localhost:8000, load against http://localhost:8002 (test secrets, throwaway state).

| ID | Title | Result | Notes |
|---|---|---|---|
| P7-01 | Attack smoke | PASS | 41 of 41 passed. Server errors (5xx): 0. |
| P7-02 | Peak-evening load | PASS | / all / 1631 / 0 / 0.034 / 0.228 / 2.098 / 2.322 / 52.9 requests/s |
| P7-03 | CGNAT | PASS | 1 passed, 6 deselected, 1 warning in 6.34s |
| P7-04 | Made-up tokens | PASS | 1 passed, 6 deselected, 1 warning in 1.65s |
| P7-05 | No secrets in the repo | PASS | 1 passed, 6 deselected, 1 warning in 2.06s |
| P7-06 | Backup restore | PASS | encrypted True; integrity ok; counts match True (3 homes) |
| P7-07 | Packages pinned with hashes | PASS | 37 packages hashed; No known vulnerabilities found |
| P7-08 | Container hardening | PASS | base images by digest: ok; require-hashes: ok; non-root USER: ok; uvicorn flags: ok; .env and state ignored: ok |
| P7-09 | Deploy and incident docs | PASS | DEPLOY 6668 chars; INCIDENT 4879 chars, DRAFT |
| P7-10 | Checks | PASS | ruff: ok; mypy: ok; bandit: ok; pip-audit: ok; tests: ok (215 passed, 1 warning, 13 subtests passed in 16.00s) |

**10 of 10 passed.**
