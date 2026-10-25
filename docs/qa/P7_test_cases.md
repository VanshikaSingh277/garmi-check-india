# Phase 7 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type.
Runner: `python tests/qa/p7_qa.py`, with two servers you run yourself (test secrets, throwaway state, `HOUSEHOLDS_ENABLED=true`):
- `QA_BASE`: default limits;
- `QA_LOAD_BASE`: `RATE_STATELESS_PER_MIN` set high, because the load comes from one machine.

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P7-01 | Attack smoke | QA_BASE | `python scripts/attack_smoke.py $QA_BASE` | Every check passes; 0 server errors; nothing echoed; security headers on every answer | High | Security |
| P7-02 | Peak-evening load | QA_LOAD_BASE | `python scripts/peak_load.py $QA_LOAD_BASE --users 50 --seconds 30` | No 5xx; errors ≤ 1%; p95 ≤ 1.5 s | High | Performance |
| P7-03 | CGNAT | — | `tests/test_p7_release.py::test_cgnat…` | 40 homes × 10 requests from one IP: all 200; requests without a token still limited at 300/min | High | Security |
| P7-04 | Made-up tokens | — | `test_made_up_tokens…` | After 30 bad tokens a minute the IP gets 429 with Retry-After, worker routes included | High | Security |
| P7-05 | No secrets in the repo | — | `test_no_secret_shaped_strings…` | No secret-shaped strings in tracked or committable files (`.env` files are never opened) | High | Security |
| P7-06 | Backup restore | QA state folder | `python -m app.backup make`, then `restore` into a new file | Backup is encrypted; restored copy passes `integrity_check`; row counts match | High | Ops |
| P7-07 | Packages pinned with hashes | — | Read `apps/api/requirements.lock`; `pip-audit --no-deps --disable-pip -r requirements.lock` | Every line has `--hash=sha256:`; no known vulnerabilities | High | Supply chain |
| P7-08 | Container hardening | — | Read `Dockerfile`, `.dockerignore` | Base images by digest; `--require-hashes`; non-root `USER`; `--no-access-log`, `--no-server-header`, `--no-proxy-headers`; `.env` and state excluded | High | Security |
| P7-09 | Deploy and incident docs | — | Open `docs/DEPLOY.md`, `docs/INCIDENT.md` | Both exist; INCIDENT is marked DRAFT with TO VERIFY timelines | Medium | Ops |
| P7-10 | Checks | — | ruff, mypy, bandit, pip-audit, full tests | All clean | High | Functional |
