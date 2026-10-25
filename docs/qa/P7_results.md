# Phase 7 test results

Run 2026-10-25 15:48: attack against http://localhost:8000, load against http://localhost:8002 (test secrets, throwaway state).

| ID | Title | Result | Notes |
|---|---|---|---|
| P7-01 | Attack smoke | PASS | 41 of 41 passed. Server errors (5xx): 0. |
| P7-02 | Peak-evening load | PASS | / all / 1573 / 0 / 0.050 / 0.265 / 2.228 / 2.451 / 50.8 requests/s |
| P7-03 | CGNAT | PASS | 1 passed, 3 deselected, 1 warning in 6.38s |
| P7-04 | Made-up tokens | PASS | 1 passed, 3 deselected, 1 warning in 1.80s |
| P7-05 | No secrets in the repo | PASS | 1 passed, 3 deselected, 1 warning in 2.13s |
| P7-06 | Backup restore | PASS | encrypted True; integrity ok; counts match True (59 homes) |
| P7-07 | Packages pinned with hashes | PASS | 37 packages hashed; No known vulnerabilities found |
| P7-08 | Container hardening | PASS | base images by digest: ok; require-hashes: ok; non-root USER: ok; uvicorn flags: ok; .env and state ignored: ok |
| P7-09 | Deploy and incident docs | PASS | DEPLOY 6668 chars; INCIDENT 4879 chars, DRAFT |
| P7-10 | Checks | PASS | ruff: ok; mypy: ok; bandit: ok; pip-audit: ok; tests: ok (212 passed, 1 warning, 13 subtests passed in 32.47s) |

**10 of 10 passed.**
