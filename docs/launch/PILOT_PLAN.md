# Pilot plan (DRAFT)

Prepared after Phase 7. It starts only after `GATE_P7_launch.md` is signed "go". The team runs the pilot; nothing here is done by the build.

## Scope

- **Who:** one RWA (resident welfare association) and one ASHA worker in Jaipur.
- **When:** February–March, before peak heat. The dates are for the team to set.
- **How long:** two weeks.
- **Size:** the team decides the number of homes. Start with the test allow-list, then everyone in the pilot.
- **What's on:**
  - WhatsApp PIN sign-up and SMS/WhatsApp evening alerts;
  - assisted mode for the ASHA worker;
  - the worker brief.
- **What stays off:**
  - saved homes in the app (`HOUSEHOLDS_ENABLED`), until the frontend prerequisite is done;
  - IMD warnings (`IMD_ENABLED`), until onboarding;
  - push, until the Firebase and VAPID keys exist.

## Setup steps

1. **Deploy** as in `docs/DEPLOY.md`, with `ENV=prod`, `ALERTS_ENABLED_GLOBAL=false` and the production secrets.
2. **Create the org and invite its admin** (CLI only):
   ```
   python -m app.admin create-org --name "<org name>" --type <rwa|ngo|health_dept|school|other> [--state "Rajasthan"] [--district-id <id>]
   python -m app.admin invite-admin --org <org_id> --name "<admin name>" --phone <admin's +91 number>
   ```
   Use `rwa` for the RWA and `health_dept` (or `ngo`) for the ASHA worker's org. The admin signs in by OTP.
3. **Invite the worker.** The admin adds the ASHA worker (`POST /api/v1/orgs/{org_id}/workers`). The worker signs in by OTP and adds homes, reading the approved consent script aloud in the family's language.
4. **Sign up households** through the WhatsApp PIN-code flow. The RWA poster shows the Thandak WhatsApp number; the family messages it, sends their 6-digit PIN code, replies YES to the consent notice, then picks a language and alert level. The poster wording needs the same approval as the other templates.
5. **Turn alerts on in two stages:**
   1. The team sets `ALERT_TEST_ALLOWLIST` to the pilot team's own numbers and sets `ALERTS_ENABLED_GLOBAL=true`. Watch two evenings: quiet hours hold, one alert per day per channel, STOP works.
   2. Clear the allow-list so everyone who signed up gets alerts.

## Daily 5-minute check (a named team member, every day of the pilot)

| Where | Look at | Act if |
|---|---|---|
| Sentry | New errors | Any new error type: open a ticket. An error touching alerts: see Rollback |
| `/internal/metrics` (job secret) | Alerts sent, failed and opened; weather budget used; weather errors | Failures above 5%; budget above 80%; any weather errors on a hot day |
| `/internal/metrics` | OTP cap used today | Above 80% of `OTP_DAILY_CAP` |
| Metrics or the database | STOP and opt-out count | More than 2 a day, or any complaint: read the alert text again |
| Jobs log | `evening_alerts`, `send_queue` and `backup` ran | A missing run |

## Success measures (the team sets the targets before day 1)

| Measure | Source | Target |
|---|---|---|
| Delivery rate (alerts delivered / sent) | Provider status webhooks → metrics | `<team>` |
| Opt-out rate (STOP / homes) | `consent_event` | `<team>` |
| Opens (WhatsApp read receipts or app opens) | Metrics | `<team>` |
| "Could not sleep" feedback trend | Daily feedback (`gov` aggregates, among Thandak users) | Falling or flat on hot nights |
| Errors per day | Sentry | `<team>` |
| Worker feedback (does the brief help?) | A short call with the ASHA worker at the end of each week | Qualitative |

## Rollback

- **The switch:** `ALERTS_ENABLED_GLOBAL=false` and restart the API and jobs containers (about one minute). Nothing already queued is sent once it is off.
- **Who flips it:** `<incident lead from docs/INCIDENT.md>`, or the backup person. Anyone on the team can ask them to.
- **When:** a wrong alert, an alert in quiet hours, a provider problem, or anything in `INCIDENT.md` S1/S2.
- **How to tell the pilot users:**
  - Use the approved "alerts paused" WhatsApp/SMS template (TEAM_TODO: write and approve it).
  - Tell the RWA committee and the ASHA worker directly.

## Incidents

Follow `docs/INCIDENT.md`: roles, severity, the first hour, notices to the Board, affected people and CERT-In.

## Go / no-go for opening wider (after two weeks)

Go wider only if all of these hold:
- No S1 incident, and every S2 closed with a regression test.
- Delivery, opt-out and error targets met.
- No alert sent in quiet hours, and none sent twice in a day on a channel.
- The RWA and the ASHA worker would continue.
- The ambulance numbers for the next states or districts are verified (`TEAM_TODO`).
- A load run sized for the wider rollout passes (TEAM_TODO: expected users), and the p99 delay in `GATE_P7_launch.md` is explained.

## Sign-off

| Reviewer | Date | Decision (start / not yet) | Notes |
|---|---|---|---|
| | | | |
