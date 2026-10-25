# Phase 5 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type.
Runner: `python tests/qa/p5_qa.py <server-log>` against a server started with **test** secrets (including `PERSON_ENC_KEYS`) and a throwaway state folder; the runner creates two orgs with the CLI. Made-up numbers only.

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P5-01 | Org and first admin only by CLI | — | `python -m app.admin create-org …`, `invite-admin …`; look for any HTTP route that creates an org | CLI works; no HTTP route creates an org | High | Security |
| P5-02 | Worker sign-in by OTP | P5-01 | Admin: OTP send + verify with purpose `worker_login` | Session token; admin session lasts 12 h | High | Functional |
| P5-03 | No number probing | — | OTP send `worker_login` for a number that isn't a worker | Same answer as for a worker; no SMS sent; verify fails | High | Security |
| P5-04 | Admin invites workers | P5-02 | POST /api/v1/orgs/{org}/workers ×2 | 201 each; same number twice → 409 | High | Functional |
| P5-05 | Worker adds a home with the consent script | Worker signed in | POST /api/v1/workers/me/households with people (nicknames, conditions, medicines) | 201; consent event `given` by worker | High | Functional |
| P5-06 | People encrypted at rest | P5-05 | Read the database file | No nickname, condition or medicine text in clear | High | Privacy |
| P5-07 | Worker isolation | P5-05, a second worker | Second worker: PATCH / DELETE the first worker's home; list | 404; not in the list | High | Security |
| P5-08 | Org isolation | Second org's admin | Reassign the first org's home | 404 | High | Security |
| P5-09 | Access log | P5-05 | List, brief, edit the home | `access_log` rows view, brief, edit, create for that worker | High | Privacy |
| P5-10 | Reassignment | Admin | PATCH /api/v1/orgs/{org}/households/{id} to the second worker | First worker 404, second 200 | Medium | Functional |
| P5-11 | Deactivation revokes sessions | Admin | PATCH worker `active: false`; that worker calls /workers/me | 401 | High | Security |
| P5-12 | Brief has no health details | P5-05 | GET /api/v1/workers/me/brief?format=text | Nicknames, place, actions; no condition or medicine words | High | Privacy |
| P5-13 | Delete on the family's request | P5-05 | DELETE the home | 204; people gone; consent event `deleted` by worker | High | Privacy |
| P5-14 | Logs hold no names or numbers | Server log | Read the log after P5-01..13 | No nickname, phone or token | High | Privacy |
| P5-15 | Automated isolation tests | — | `tests/test_worker.py` | Pass | High | Security |
