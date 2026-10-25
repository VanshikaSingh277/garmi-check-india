# Build progress
Current step: 5          Current phase: 1
Next action: Phase 1 on `backend/p1-solid-api`, in the order of PHASE0_PLAN §4.
Baseline tests: 77 passed, 0 failed (2026-10-24; `python tests/test_*.py` for each file). Includes the uncommitted district-normals work that was carried onto `backend/setup`.
User choices: test-case format = (asked; default ID | Title | Preconditions | Steps | Expected | Priority | Type until answered); API collection tool = (asked: Bruno or Postman); PRs = (asked: open with `gh`, or leave branches)

Decisions:
- 2026-10-25: Phase 0 STOP answered with "continue": recommendations C1–C12 accepted, Phase 1 plan (PHASE0_PLAN §4) and its dependencies (httpx; dev: pytest, ruff, mypy, bandit, pip-audit) approved. `backend/setup` not merged yet, so Phase 1 branches from it.
- 2026-10-24: The tree wasn't clean at Step 1 (district-normals work awaiting its commit). The user said to complete the kit first and commit after, so the work moved onto `backend/setup` and goes in its own commit with the message the user approved.
- 2026-10-24: `reference/thandak_v2/REWORK_PROMPT.md` moved to `docs/archive/`. The rest of `reference/thandak_v2/` stays as reference code.
- 2026-10-24: The user said "finish this kit": continued on `backend/setup` into Phase 0 without a restart.
- 2026-10-24: `env.example` also lists `ALERTS_ENABLED_GLOBAL` and `ALERT_TEST_ALLOWLIST` (from the build prompt, Steps 5 and 6) besides the spec §4 names.

Open questions for the user:
- Test-case format, Bruno or Postman, and PRs with `gh` or branches only (asked in the Step 1 message).
- `apps/web/.env.app` and `apps/web/.env.example` are tracked in git. They are the web app's build settings and weren't opened (the `.env.*` rule). Keep them tracked, or rename them so the rule doesn't apply?
- (Detail behind C1, C3–C5) conflicts with spec §2 rule 3, "UNVERIFIED and TO VERIFY are never used"; "a Design choice may only make a result more cautious"):
  - `evaporative.max_twb` (UNVERIFIED) switches the cooler and khus cards today. Spec §7.5 says those cards stay off with reason `threshold_not_verified` until the threshold is verified.
  - `heat.station_type` and `heat.normal_point` (UNVERIFIED design choices) feed the IMD departure rule.
  - `heat.normal_point` caps the departure rule at High on raised ground. A cap makes the result less cautious, which rule 3 doesn't allow for a design choice.
  - `cost.band_limits_inr` (UNVERIFIED) filters fixes by budget.
- The spec was written against `heat-india` at `a4f574e`; this repo is `garmi-check-india`. Phase 0 maps the differences.

Done:
- 2026-10-24: Phase 0. `docs/backend/PHASE0_PLAN.md` (map, §3 checks, conflicts, Phase 1 plan); commands filled in.
- 2026-10-24: Step 3. `docs/TEAM_TODO.md` filled; `docs/launch/consent_DRAFT.md` and `docs/launch/hindi_review.csv` drafted.
- 2026-10-24: Step 2. `docs/launch/APPROVALS.md`, WhatsApp and SMS templates, and the IMD access letter drafted (all DRAFT).
- 2026-10-24: Step 1. Branch `backend/setup`; kit files copied (spec, DETAILS); `.gitignore` extended; `env.example` created; tracked files scanned for secrets (none found).
