# Build progress
Current step: 5          Current phase: 6
Next action: all phases built; one commit after the user approves the message. Gates P2, P3, P5, P7 and the pilot plan wait for sign-off.
Baseline tests: 77 passed, 0 failed (2026-10-24; `python tests/test_*.py` for each file). Includes the uncommitted district-normals work that was carried onto `backend/setup`.
User choices: test-case format = default ID | Title | Preconditions | Steps | Expected | Priority | Type (not answered yet); API collection tool = Bruno (`docs/api/bruno/`, chosen by default; Postman can import it); PRs = leave branches (not answered yet)

Decisions:
- 2026-10-25: Security audit:
  - Git history and the built site have no secrets.
  - Every route's guard and ownership check was reviewed.
  - Frontend escaping gaps are closed: a missing translation key is escaped, and API values are escaped in class attributes and placeholders.
  - CSV cells that look like formulas are neutralised.
  - Production refuses to start with missing, short, reused or malformed secrets, or with no ALLOWED_HOSTS.
  - COOP header added.
  - The 7 npm advisories are in build-only tools (`@capacitor/cli`, `@capacitor/assets`) with no upstream fix; shipped code has 0.
  - The ML packages (numpy, scikit-learn, xgboost, shapely) are not upgraded before submission: no known vulnerabilities, and a major upgrade needs the room model re-validated. scikit-learn stays (XGBRegressor needs it).
- 2026-10-25: Website pages send `Referrer-Policy: strict-origin-when-cross-origin` instead of spec §8.5's `no-referrer`, because OpenStreetMap blocks tile requests without a Referer (the maps showed "Access blocked"). Only the origin is sent; the path and the #fragment holding the place never are. API answers keep `no-referrer`. The map bounds were widened so all of India fits when zoomed out.
- 2026-10-25: Phase 7: requests with a token skip the per-IP limit (CGNAT, spec §8.7), with a 30/min per-IP limit on bad tokens. The load script is `scripts/peak_load.py` because pytest collects `*_test.py`. Docker isn't on this machine, so the container runs are left for staging.
- 2026-10-25: Phase 6: room numbers stay hidden on the offset fallback even for a calibrated home (calibration is validated against the model only). IMD stays off until onboarding; the adapter reads a normalised format.
- 2026-10-25: Phase 4: the frontend prerequisite (spec §6.3) isn't done, so saved homes are built and tested but behind HOUSEHOLDS_ENABLED (off). Push senders use `cryptography` + httpx only (no new packages); Web Push matches the RFC 8291 test vector.
- 2026-10-25: No per-phase commits (user's instruction), so phases 2 onwards live uncommitted in one working tree (branch name `backend/p4-households` at the time of writing) and go into one commit at the end.
- 2026-10-25: The user asked for every phase to be built, tested with its QA pack, and continued without stopping, with one step-by-step list at the end, and no commits until the whole build is done. Gate sign-offs are prepared and left for the user.
- 2026-10-25: Phase 2: the 3-a-day test-alert limit is a per-home rate limit, because notice_log's unique key (spec §5.9) allows one test row per channel per day. Webhooks use a provider-neutral signature (HMAC over "timestamp.body") until a provider is chosen.
- 2026-10-25: Phase 1 changes of approach: (a) weather cells are 0.1° squares at Open-Meteo's cell-centre height; the per-point 100 m bucket needs a bundled terrain file, because the free elevation API counts every point (a 0.1° grid is ~32,000 calls; one attempt used up the hourly limit and was stopped); (b) sync httpx in FastAPI's threadpool instead of async (sync, CPU-bound routes; same timeout and retries); (c) `/api/where` keeps answering `in_india: false` so the current app can show "outside India", every other location route returns 422.
- 2026-10-25: FastAPI 0.115.6 → 0.162.0 and Starlette 0.41.3 → 1.10.0, because pip-audit found 14 known vulnerabilities in Starlette 0.41.3. All tests pass on the new versions.
- 2026-10-25: C3 done: the cap on uncertain hill normals is removed (stricter). C4/C5: `heat.station_type`, `heat.normal_point`, `cost.band_limits_inr` relabelled `Design choice`.
- 2026-10-25: Infant water line: WHO eLENA (read 2026-10-25) supports "not even water" for under-6-month exclusive breastfeeding but doesn't mention heat; spec §7.3's "even in heat" is left out until a source is found (TEAM_TODO).
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
- 2026-10-25: Step 8: docs/launch/PILOT_PLAN.md (DRAFT).
- 2026-10-25: Phase 7 built (uncommitted): 212 tests, QA 10/10, attack 41/41, load pass; GATE_P7_launch.md prepared.
- 2026-10-25: Phase 6 built (uncommitted): 208 tests, QA 12/12; calibration validated ("ship") before use.
- 2026-10-25: Phase 5 built (uncommitted): 170 tests, QA 15/15; GATE_P5_privacy.md prepared.
- 2026-10-25: Phase 4 built (uncommitted): 164 tests, QA 14/14.
- 2026-10-25: Phase 3 built (uncommitted): 153 tests, golden cases 12/12, QA 11/11; GATE_P3_safety.md generated.
- 2026-10-25: Phase 2 built (uncommitted): 132 tests and 19/19 QA cases pass; gate file prepared.
- 2026-10-25: Phase 1 QA pack run: 28/28 (`docs/qa/P1_results.md`).
- 2026-10-25: Phase 1 built on `backend/p1-solid-api` (report in `docs/backend/REPORTS.md`, QA pack `docs/qa/P1_test_cases.md`, Bruno collection `docs/api/bruno/`).
- 2026-10-24: Phase 0. `docs/backend/PHASE0_PLAN.md` (map, §3 checks, conflicts, Phase 1 plan); commands filled in.
- 2026-10-24: Step 3. `docs/TEAM_TODO.md` filled; `docs/launch/consent_DRAFT.md` and `docs/launch/hindi_review.csv` drafted.
- 2026-10-24: Step 2. `docs/launch/APPROVALS.md`, WhatsApp and SMS templates, and the IMD access letter drafted (all DRAFT).
- 2026-10-24: Step 1. Branch `backend/setup`; kit files copied (spec, DETAILS); `.gitignore` extended; `env.example` created; tracked files scanned for secrets (none found).
