# External approvals

These take days to weeks. Phase 2 can't send anything real until the WhatsApp and SMS rows are done; until then it runs against a fake provider with `ALERTS_ENABLED_GLOBAL` off. Nothing here has been submitted.

| Item | Why | Needed by phase | What to submit | Status | Notes |
|---|---|---|---|---|---|
| WhatsApp Business provider account + business verification | Evening alerts and the no-app sign-up (spec §6.5) go out on WhatsApp | 2 | Pick one Indian BSP (Business Solution Provider); legal entity documents; display name; the number to use; Meta business verification | Not started | The sign-up is user-initiated (they message first), so only alert messages need approved templates |
| WhatsApp template approval | Business-initiated messages (evening alert, morning work alert, retention "reply YES") must use approved templates | 2 | The templates in `templates/whatsapp_alerts.md`, once the team approves the DRAFT wording | Not started | Category "Utility". No health details in any template (spec §2 rule 7) |
| SMS DLT registration: entity | TRAI rules: every commercial SMS sender in India must be registered on a DLT platform | 2 | Entity registration (PAN, incorporation or registration certificate, authorised signatory letter) on one operator's DLT portal | Not started | One registration works across operators |
| SMS DLT: sender ID (header) | Messages carry a 6-character header | 2 | Proposed header, e.g. a 6-letter form of the name; proof of the brand | Not started | Choose a "transactional / service-implicit" category |
| SMS DLT: templates | Every SMS text must match a registered template | 2 | The templates in `templates/sms_dlt.md` with `{#var#}` placeholders | Not started | Hindi is Unicode: 70 characters per single SMS, 67 per part when split (GSM English: 160 / 153) |
| SMS provider account | Sending through the DLT-registered entity | 2 | Account with one Indian SMS gateway; link the DLT entity ID, header and template IDs | Not started | Keys go in `SMS_API_KEY` etc. in your own environment, never in the repo |
| IMD API access | Official district heat warnings (spec §7.1: our level never below IMD's) | 6 | The letter in `imd_access_request.md`, with the server's fixed outbound IP | Not started | IMD allow-lists IPs, so hosting must have a static egress IP |
| Weather: Open-Meteo paid plan or self-hosting | The free API is for non-commercial use only and is limited to under 10,000 calls a day, 5,000 an hour and 600 a minute (Open-Meteo terms); the historical/archive API is also free only for non-commercial use | 2 (prefetch job) | Either a subscription (key in `OPEN_METEO_API_KEY`) or a self-hosted Open-Meteo instance | Not started | See the call budget below |
| Push: Firebase project (FCM) | App push on Android, and iOS through FCM | 4 | A Firebase project; Android app id `in.thandak.app`; service-account JSON goes in `FCM_CREDENTIALS_JSON` in your environment | Not started | |
| Push: Apple push key (APNs) | iOS push | 4 | Apple Developer account; an APNs auth key (.p8) uploaded to Firebase | Not started | Needs the paid Apple Developer Program |
| Hosting | HTTPS behind a CDN or WAF, with a writable volume for the database (spec §4, §8.10) | 2 | Provider choice; domain; TLS; a persistent volume (e.g. `/var/lib/thandak/`); static egress IP for IMD; encrypted object storage for backups (14 days) | Not started | Run as non-root with a read-only root filesystem |

## Weather call budget (estimate)

How Open-Meteo counts: one request is 1 call if it has at most 10 variables and at most 2 weeks of data; more counts as fractions of extra calls (Open-Meteo pricing page). Our forecast request (7 forecast days + 2 past days, about 6 variables) is **1 call**.

A cell is lat/lon rounded to 0.1° (about 11 × 11 km) plus a 100 m elevation bucket (spec §4).

| Source of calls | Formula | Pilot: one RWA + one ASHA worker in Jaipur | Wider: alert homes in 2,000 cells |
|---|---|---|---|
| `prefetch_forecasts` (17:30 and 05:30, alert-enabled cells only, spec §9) | 2 × alert cells | about 20 cells → 40/day | 4,000/day |
| App traffic (cached on demand per cell; a cell refetches at most once per cache period) | active cells × refetches per day | about 20 cells × up to 48 → under 1,000/day | depends on users; up to 48 per active cell per day with a 30-minute cache |
| Hill point normals (archive API, once per new ~5 km cell at 600 m or more; cached on disk) | about 11 calls per new hill cell | 0 (Jaipur is below 600 m) | one-off, then cached |

What this means:
- **The pilot fits the free tier's call limits**, but only if Thandak counts as non-commercial (Open-Meteo: private or non-profit apps without ads or subscriptions). Confirm this before the pilot.
- **Going wider needs a paid plan or self-hosting.** 4,000 prefetch calls plus app traffic gets close to, or past, 10,000 a day.
- Set `WEATHER_DAILY_BUDGET` to the plan's limit. At 90% of it, the app stops adding new cells and serves the nearest cached cell within 25 km (spec §4).

These are planning estimates, not measurements. Phase 2's `/internal/metrics` will report the real numbers.
