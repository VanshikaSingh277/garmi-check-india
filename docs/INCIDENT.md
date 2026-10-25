# Incident response (DRAFT)

The breach and outage plan (spec §8.12). **DRAFT.** The names, contacts and legal timelines must be filled in and approved by the team and legal before launch (TEAM_TODO). Until then, a role in angle brackets means "not assigned yet".

## 1. Roles

| Role | Who | Backup | Decides |
|---|---|---|---|
| Incident lead | `<name, phone>` | `<name>` | Severity, switching features off, when it is over |
| Technical lead | `<name>` | `<name>` | Containment and fixes, key rotation, restore |
| Grievance / data protection officer | `<name, contact in the consent notice>` | `<name>` | Whether this is a personal-data breach; notices to the Board and to people |
| Comms | `<name>` | `<name>` | Messages to users, partner orgs (RWA, ASHA/NGO), press |

One person can hold two roles in the pilot. The incident lead role must always be filled.

## 2. Severity

| Level | Examples | Response |
|---|---|---|
| **S1** | Phone numbers, tokens, worker-managed person data or backups exposed; a wrong alert sent to many people; an alert sent during quiet hours | Start within 30 minutes, any time of day |
| **S2** | Alerts not sent on a hot evening; API down longer than 30 minutes; weather data stale on a red/orange day | Start within 2 hours |
| **S3** | One feature broken; a single wrong text | Next working day |

## 3. First hour (S1)

1. **Open a log.** Use a private doc with times in IST: what was seen, who did what, and when.
2. **Stop the harm.** Pick the switch for the problem (each one is a setting plus a restart, about one minute):
   - wrong or unexpected alerts: `ALERTS_ENABLED_GLOBAL=false`
   - saved homes: `HOUSEHOLDS_ENABLED=false`
   - IMD data looks wrong: `IMD_ENABLED=false`
   - worker misuse: the org admin deactivates the worker (`PATCH /api/v1/orgs/{org_id}/workers/{worker_id}` with `{"active": false}`), which revokes every session. If the admin account itself is at risk, set `TOKEN_PEPPER` to a new value, which signs everyone out
   - the jobs container can be stopped on its own without taking the API down
3. **Contain a leak.**
   - Rotate whatever leaked: `TOKEN_PEPPER` (signs everyone out), `PHONE_ENC_KEYS` / `PERSON_ENC_KEYS` (new key first), `INTERNAL_JOB_SECRET`, the webhook secrets, the provider API keys.
   - Revoke the provider keys in the provider's console.
4. **Keep the evidence.** Save the API and jobs logs, Sentry events and `access_log` rows for the affected period. Logs hold no phone numbers, tokens or coordinates; IPs appear only as a hashed tag.
5. **Decide whether it is a personal-data breach.** The grievance officer decides, with the incident lead. If it is, start section 4 now; don't wait for the fix.

## 4. Notices (TO VERIFY with legal before launch)

These timelines come from the team's reading of the law. **TO VERIFY:** legal must confirm each one against the current text, then add the rule reference here.

| To | When | What |
|---|---|---|
| Data Protection Board of India (DPDP Act 2023 and DPDP Rules) | TO VERIFY: an intimation without delay, then a detailed report within 72 hours | What happened, when, what data, how many people, what was done, the contact |
| Affected people (DPDP Rules) | TO VERIFY: without delay | In plain language, in English and Hindi, by the channel they use (WhatsApp/SMS/app): what happened, what it means for them, what they can do, the contact. Templates need approval like every other message |
| CERT-In (CERT-In directions of 28 April 2022) | TO VERIFY: within 6 hours of noticing a reportable incident | The CERT-In incident form |
| Partner orgs (RWA, NGO, ASHA supervisor) | Same day for anything touching their homes or workers | What happened and what they should tell families |
| Providers (WhatsApp/SMS, Firebase, hosting) | When their keys or service are involved | Per their terms |

## 5. Fix and recover

- Fix the cause and add a regression test before the fix (one regression test per bug).
- If data was lost or damaged, restore from the last good backup (`docs/DEPLOY.md` §6).
- Turn the switches back on one at a time: the test allow-list first, then everyone.

## 6. Afterwards (within 5 working days)

- **Write a review:** timeline, cause, impact (how many homes, which data), what worked, and what changes. Keep it blameless.
- **Update** this file, `docs/DEPLOY.md` and the tests.
- **Check retention:** deleted data leaves the backups within 14 days, as the consent notice says. Don't keep extra copies of leaked data beyond what the investigation needs.

## Contacts

| Who | Contact |
|---|---|
| Incident lead | `<to fill>` |
| Grievance officer | `<to fill, same as the consent notice>` |
| Hosting provider support | `<to fill>` |
| WhatsApp / SMS provider support | `<to fill once chosen>` |
| CERT-In | `<to fill from cert-in.org.in>` |
| Data Protection Board | `<to fill from the Board's official site>` |
