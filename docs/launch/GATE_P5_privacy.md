# Gate after Phase 5: privacy review (assisted mode)

Health workers will hold details about families who may have no phone, so the team checks isolation and logging by hand before any worker uses it, and signs off below.

## Automated results (2026-10-25)
- `tests/test_worker.py`: 6 passed. It covers:
  - isolation between workers in one org and between orgs;
  - reassignment and deactivation (sessions revoked);
  - `access_log` rows;
  - OTP sign-in that doesn't reveal whether a number is a worker;
  - encryption at rest;
  - brief text with no health details, including the nickname fallback.
- QA pack `docs/qa/P5_results.md`: 15 of 15 against a live server with test secrets.

## Manual steps for you (use test numbers and a test database, never real families)
1. Create two orgs and their admins with the CLI:
   `python -m app.admin create-org --name "Test A" --type ngo --state Delhi`, then `invite-admin --org <id> --name "Admin A" --phone <test number>`; repeat for "Test B".
2. Sign in as Admin A (OTP, purpose `worker_login`), invite two workers W1 and W2; sign in as both. Sign in as Admin B and invite W3.
3. As W1, add a household with two people (nicknames, a condition and a medicine class).
4. Try to read or change it:
   - as W2: list, PATCH and DELETE must give 404, and it must not appear in W2's list;
   - as W3 (other org): the same;
   - as Admin B: PATCH `/api/v1/orgs/<org B>/households/<id>` must give 404.
5. Open the database (`<state>/thandak.db`) and check the `access_log` table: one row per view, brief, edit, create, with W1's id. Check `person`: the nickname, conditions and medicines are unreadable bytes.
6. As W1, fetch `/api/v1/workers/me/brief?format=text`. Confirm it shows nicknames, place and actions only: no condition, medicine or pregnancy words.
7. As Admin A, deactivate W1 (`PATCH /api/v1/orgs/<org A>/workers/<W1>` `{"active": false}`) and confirm W1's token now gets 401.
8. Decide on the open DPDP item (children's data entered by a worker, `docs/TEAM_TODO.md`) and approve the read-aloud script (`docs/launch/consent_DRAFT.md`, then set `CONSENT_SCRIPT_VERSION`).

## Checklist

| Check | Result |
|---|---|
| A worker can't see or change another worker's homes | |
| A worker or admin can't touch another org's homes | |
| Every read and write is in `access_log` | |
| People's nicknames, conditions and medicines are encrypted at rest | |
| The text brief has no health details | |
| Deactivating a worker ends their sessions | |
| The consent script is approved and its version set | |
| The DPDP children's-data question is answered | |

## Sign-off

| Reviewer | Date | Decision (go / fix first) | Notes |
|---|---|---|---|
| | | | |
