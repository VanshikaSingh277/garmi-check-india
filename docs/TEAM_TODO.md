# Team to-do

Things only the team can supply. The build never fills these from memory (spec §2 rule 1). A feature that needs a missing item stays off until it is supplied.

| Item | File / row it fills | Format needed | Owner | Status |
|---|---|---|---|---|
| Ambulance number for every state and UT (table below) | `data/emergency_numbers.csv` (Phase 1, spec §6.2) | state, number, service name, source URL (state health dept or NHM page), date checked | Team | Open (Delhi seeded) |
| Final consent notice, English and Hindi, with a grievance contact | `docs/launch/consent_DRAFT.md` → approved version | Approved text, version number, grievance officer name and contact | Team + legal | Draft ready |
| Worker read-aloud consent script, English and Hindi | `docs/launch/consent_DRAFT.md` (second part) | Approved text and `script_version` | Team + legal | Draft ready |
| WhatsApp and SMS alert templates | `docs/launch/templates/whatsapp_alerts.md`, `sms_dlt.md` | Approved wording; WhatsApp template names; DLT template IDs | Team | Draft ready |
| Hindi review of new lines | `docs/launch/hindi_review.csv` | reviewer and status filled per row | Native Hindi reviewer | Open |
| Delhi's 2022 ward boundaries (250 wards) | replaces `apps/api/data/wards.geojson` (pre-2022, 290 units) | GeoJSON with ward number and name, plus source and licence | Team | Open |
| Hill and coastal list, checked against IMD's classification | `verified_numbers.csv` row `heat.station_type` (now: hill ≥ 1000 m, coast ≤ 30 km, a design choice) | Which districts or stations IMD treats as hill and coastal, with the IMD source | Team | Open |
| IMD station May normals used as spot checks | `apps/api/data/district_normals_checks.json`, `verified_numbers.csv` rows `imd.normal_tmax`, `heat.normal_point` | IMD's published 1991–2020 normal maximum for Delhi (Safdarjung), Jaipur, Chennai, Nagpur, Ahmedabad, Shimla, Srinagar, Leh, Darjeeling, Shillong, Ooty, Mussoorie, Gangtok, Dehradun, Bengaluru, Pune, with source | Team | Open (current values are approximate) |
| DPDP: children's data in worker-registered homes | spec §8.12; decides Phase 5 consent flow | What the DPDP Rules require for a child's data entered by a health worker (guardian consent, verifiable or not), with the rule reference | Team + legal | Open |
| `evaporative.max_twb` (afternoon wet-bulb 24 °C that switches cooler and khus advice) | `verified_numbers.csv` | A source for the wet-bulb (or RH) above which desert coolers and wet screens stop helping, or a decision to keep the cards off | Team | UNVERIFIED |
| `heat.station_type` (hill ≥ 1000 m, coast ≤ 30 km) | `verified_numbers.csv` | IMD's operational definition, or approval as a labelled design choice | Team | UNVERIFIED |
| `heat.normal_point` (point normals from 600 m up; departure rule capped at High there) | `verified_numbers.csv` | Approval of the method, or a better normal source for hill towns | Team | UNVERIFIED |
| `cost.band_limits_inr` (low < ₹5,000, medium ≤ ₹50,000) | `verified_numbers.csv` | Local price check | Team | UNVERIFIED |
| `cost.lime_per_kg` (₹3–8 per kg) | `verified_numbers.csv` | A current price source | Team | UNVERIFIED |
| `fan.limit.skin_wetting` | `verified_numbers.csv` | A numeric limit with a source, if one exists | Team | UNVERIFIED |
| `greening.surface_drop` | `verified_numbers.csv` | A number and source | Team | To verify |
| `wet_bulb.danger` WHO value, `mortality.india.heatwave` Delhi cut-off, `mortality.delhi.ihi` cut-offs | `verified_numbers.csv` (the parts marked UNVERIFIED inside Verified rows) | Source, or confirm none exists | Team | UNVERIFIED parts |
| Sources for 8 fixes shown as "general advice" | `apps/api/data/fixes.json`: `fam_cooler_dry`, `fam_cooler_humid`, `fam_night_fan_pull`, `fam_wet_screen`, `col_buddy_checks`, `col_shade_structures`, `col_cool_paving`, `col_water_revival` | NDMA, NCDC or WHO page for each, or keep as general advice | Team | Open |
| Spec §7.2–7.3 numbers: AC setpoint, outdoor work-hour and water amounts | `verified_numbers.csv` (new rows, Phase 3) | Value, unit and source for each | Team | Open |
| Prices for lime, cool-roof paint and modular roofs | `verified_numbers.csv` rows `cost.lime_per_kg` (UNVERIFIED), `cost.coolroof_per_m2` and `cost.modroof_per_sqft` (both "Reported") | A current price with a primary source (state policy order, government rate list), so the row can be Verified. Until then the app shows no price (spec §2 rule 3) | Team | Open (prices hidden since Phase 1) |
| Per-point ground height inside hill weather cells | `engine/weather.py` (cells are 0.1° squares at the cell centre's height) | Choose a terrain file to bundle (e.g. a 30 arc-second DEM for India, with licence), or accept cell-centre height. The free elevation API counts every point as a call, so a national grid isn't possible on it | Team | Open |
| Infant water line: "even in heat" | `fixes.json` `fam_vulnerable_care`, `hydrate_shade`; spec §7.3 wording | A source that says exclusively breastfed babies need no water in hot weather. WHO eLENA (verified) says "not even water" but doesn't mention heat, so the app leaves "even in heat" out | Team | Open |
| Model card date | `apps/api/data/indoor_model_card.json` (`/api/version` returns `model_card_date: null`) | The date the room model was trained and validated | Team | Open |
| WhatsApp and SMS provider choice | `apps/api/app/messaging.py` (only the fake sender exists) | Provider name, API docs, how it signs webhooks; then a real adapter is built behind `messaging.Provider` | Team | Open (blocks real alerts) |
| Approve the message texts | `apps/api/data/message_templates.json` (`"status": "DRAFT"` → `"approved"`) | Approved English and Hindi wording; WhatsApp template names; DLT template IDs | Team | Draft ready |
| Production secrets | Your environment or secret store (names in `env.example`) | `TOKEN_PEPPER`, `PHONE_ENC_KEYS` (32-byte keys, base64), `PHONE_HMAC_KEY`, `PERSON_ENC_KEYS`, `INTERNAL_JOB_SECRET`, `WHATSAPP_WEBHOOK_SECRET`, `SMS_WEBHOOK_SECRET`, `BACKUP_ENC_KEY`, `LOG_HASH_SECRET` | Team | Open |
| `OTP_DAILY_CAP` | Environment | A daily limit for codes sent (default 500, a guess) that fits the SMS budget | Team | Open |
| Default outdoor work window | `apps/api/engine/today.py` `WORK_DEFAULT` (06:00–19:00) | Confirm, or give the hours to use when a worker doesn't say | Team | Design choice |
| Frontend prerequisite for saved homes | Website and app code; then `HOUSEHOLDS_ENABLED=true` | Escape-by-default templating on the website; the household token in Keychain/Keystore in the app (spec §6.3) | Frontend | Open (blocks saved homes) |
| Firebase and APNs for app push | Environment: `FCM_CREDENTIALS_JSON` | A Firebase project, its service-account JSON, and an APNs key uploaded to Firebase for iOS | Team | Open |
| Web push keys | Environment: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | A P-256 key pair (base64url) and a contact (mailto: or https:) | Team | Open |
| Doctor / public-health review of the per-person texts | `docs/launch/GATE_P3_safety.md`, `apps/api/data/actions.json` | Signed decision in the gate file | Team + reviewer | Open |
| IMD district warnings feed | `apps/api/app/imd.py`; environment `IMD_ENABLED`, `IMD_API_BASE`, `IMD_API_KEY` | API access from IMD (letter in `docs/launch/imd_access_request.md`), its format, and how its district names map to ours | Team | Open (IMD warnings off) |
| Smallest count shown in government numbers | Environment `AGG_MIN_COUNT` (default 10) | Confirm 10, or the number the team or legal chooses | Team + legal | Design choice |
| Who may see government numbers | `/api/v1/gov/today`, `/api/v1/gov/trend` (public now) | Keep public, or require a login for officials | Team | Open |
| Hosting, HTTPS/CDN and object storage for backups | `docs/DEPLOY.md` §3, §6 | Provider, region (India), bucket with 14-day retention, and the two people who can read backups | Team | Open (blocks deploy) |
| Incident roles, contacts and legal timelines | `docs/INCIDENT.md` (DRAFT; timelines TO VERIFY) | Names and phones per role; legal's confirmation of the DPDP Board, affected-people and CERT-In timelines with rule references | Team + legal | Open (blocks launch) |
| Expected users at launch | `scripts/peak_load.py` target, `RATE_STATELESS_PER_MIN` | Homes and peak-evening requests expected, to size the load test and the server | Team | Open |
| "Alerts paused" message | `apps/api/data/message_templates.json` (new template) | Approved English and Hindi text for telling pilot users alerts are paused | Team | Open |
| Pilot targets | `docs/launch/PILOT_PLAN.md` success measures | Targets for delivery rate, opt-out rate, opens and errors per day | Team | Open |
| p99 delay of about 2 s in the load test | `docs/launch/GATE_P7_launch.md` | Decide whether to investigate before the pilot (about 1 request in 100) | Team | Open |

## Ambulance numbers by state and UT

Re-check every row before launch. Only rows marked Verified are shown in the app; everywhere else the app shows 112 alone.

| State / UT | Ambulance number | Service | Source URL | Checked | Status |
|---|---|---|---|---|---|
| Andhra Pradesh | | | | | Open |
| Arunachal Pradesh | | | | | Open |
| Assam | | | | | Open |
| Bihar | | | | | Open |
| Chhattisgarh | | | | | Open |
| Goa | | | | | Open |
| Gujarat | | | | | Open |
| Haryana | | | | | Open |
| Himachal Pradesh | | | | | Open |
| Jharkhand | | | | | Open |
| Karnataka | | | | | Open |
| Kerala | | | | | Open |
| Madhya Pradesh | | | | | Open |
| Maharashtra | | | | | Open |
| Manipur | | | | | Open |
| Meghalaya | | | | | Open |
| Mizoram | | | | | Open |
| Nagaland | | | | | Open |
| Odisha | | | | | Open |
| Punjab | | | | | Open |
| Rajasthan | | | | | Open |
| Sikkim | | | | | Open |
| Tamil Nadu | | | | | Open |
| Telangana | | | | | Open |
| Tripura | | | | | Open |
| Uttar Pradesh | | | | | Open |
| Uttarakhand | | | | | Open |
| West Bengal | | | | | Open |
| Andaman and Nicobar Islands | | | | | Open |
| Chandigarh | | | | | Open |
| Dadra and Nagar Haveli and Daman and Diu | | | | | Open |
| Delhi | 102 | CATS | https://cats.delhi.gov.in/faqs | | Seeded, re-check before launch |
| Jammu and Kashmir | | | | | Open |
| Ladakh | | | | | Open |
| Lakshadweep | | | | | Open |
| Puducherry | | | | | Open |
