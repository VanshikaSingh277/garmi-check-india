# Gate P7: launch review

Prepared 2026-10-25 after Phase 7. All results below come from local runs: test secrets, a throwaway database and the live Open-Meteo forecast. **Nothing has been deployed.** Repeat sections 1–3 against the real container on staging before go (`docs/DEPLOY.md` §7).

## 1. Results

| Check | Result | Details |
|---|---|---|
| Attack smoke (`scripts/attack_smoke.py`) | **41 of 41**, 0 server errors | `docs/launch/attack_smoke_results.md`. Covers bad bodies (413/415/422, including 5,000-deep JSON), hostile strings, SQL, path traversal, docs off, internal routes, made-up tokens, unsigned/replayed webhooks, Host and CORS, TRACE, and the 429 flood |
| Load at the evening-peak mix (`scripts/peak_load.py`) | **Pass**: 4,061 requests in 61 s (67/s), 0 errors | `docs/launch/load_test_results.md`. 50 simulated people, 40 saved homes. p50 0.024 s, p95 0.13 s, **p99 2.0 s**. About 1 request in 100 waits about 2 s. The cause hasn't been found yet (SQLite write contention or the weather cache are the likely places). Look into it before more traffic, not a blocker for a pilot |
| Backup and restore | **Pass** | An encrypted backup of the QA database (60 homes) restored into a new file. `integrity_check` ok; counts match. Also tested in Phase 2 |
| CGNAT (spec §10.3) | **Pass** | 40 homes × 10 requests from one IP are all answered. A fix was needed for this: requests with a token were also counted against the 300/min IP limit, so they now skip it. Made-up tokens put the IP back under a limit (30 a minute) |
| No secrets in the repo | **Pass** | All 369 tracked or committable text files scanned. `.env` files are never opened |
| `bandit` | 0 issues | `app`, `engine`, `main.py` |
| `pip-audit` | No known vulnerabilities | Both `requirements.txt` and the full hash-pinned `requirements.lock` (37 packages) |
| Tests | 212 passed | Plus QA packs P1–P7 (`docs/qa/`) |

## 2. Hardening in place

- **Base images:** pinned by digest.
- **Packages:** installed with `--require-hashes`.
- **Container:**
  - a non-root user;
  - code and data are read-only;
  - designed for a read-only root filesystem, with `/state` and `/tmp` the only writable places;
  - `.env` files and state are kept out of the image.
- **Server:**
  - uvicorn runs without its access log, Server header or proxy-header rewriting;
  - our own log has no query strings, tokens, phone numbers or coordinates;
  - with `ENV=prod`, the API refuses to start if a data file doesn't match the manifest.
- **Alerts:** `ALERTS_ENABLED_GLOBAL` is off by default, with a test allow-list.

## 3. Open TEAM_TODO items that block launch

| Item | Blocks |
|---|---|
| WhatsApp/SMS provider chosen and its adapter built; DLT entity and template IDs | Any real alert or OTP |
| Approved message texts (English and Hindi) and Hindi review | Any real alert |
| Final consent notice and grievance contact; worker read-aloud script | Sign-up |
| DPDP children's-data answer | Worker-registered homes with children |
| Production secrets in a secret store (`docs/DEPLOY.md` §4) | Starting in prod |
| Hosting chosen; HTTPS, CDN/WAF; object storage for backups and who can read it | Deploy |
| `docs/INCIDENT.md` names, contacts and legal timelines (TO VERIFY) | Launch |
| Gate sign-offs P2 (dry run), P3 (doctor/public-health review), P5 (privacy) | Each feature behind its gate |
| Ambulance numbers per state (only Delhi seeded; others show 112) | Not a blocker (112 works everywhere); should be done before going wider |
| Expected users at launch, to set the load-test target | Sizing beyond the pilot |

Waiting on other teams (not blockers for an alerts-only pilot):
- the frontend prerequisite for saved homes (`HOUSEHOLDS_ENABLED`);
- Firebase/APNs and VAPID keys for push;
- IMD onboarding (`IMD_ENABLED`).

## 4. Go / no-go checklist

| # | Check | Done? |
|---|---|---|
| 1 | Staging runs the real image as in `docs/DEPLOY.md` (read-only filesystem, non-root, secrets from the store) | |
| 2 | `attack_smoke.py` passes against staging | |
| 3 | A load run against staging passes | |
| 4 | A staging backup is uploaded to object storage and restored | |
| 5 | Sentry receives a test error, with no personal data in it | |
| 6 | Gates P2, P3 and P5 are signed "go" | |
| 7 | Provider, templates, consent notice and grievance contact are approved | |
| 8 | `INCIDENT.md` is filled in and approved; the on-call person knows the rollback switch | |
| 9 | `ALERTS_ENABLED_GLOBAL=false` and the test allow-list is set by the team | |
| 10 | The pilot plan (`docs/launch/PILOT_PLAN.md`) is agreed with the RWA and the ASHA worker | |

## Sign-off

| Reviewer | Date | Decision (go / fix first) | Notes |
|---|---|---|---|
| | | | |
