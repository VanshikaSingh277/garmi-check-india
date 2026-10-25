# Gate after Phase 2: alert dry run

Before any alert reaches a real person, the team runs a dry run with its own test phones and signs off below.
Nothing has been sent to a real number yet: only the fake sender exists, which writes to `<state>/outbox.jsonl`.

## What's needed first
1. A WhatsApp provider and DLT-registered SMS (`APPROVALS.md`). The real provider adapter is built then, behind the same `messaging.Provider` interface. It must refuse templates that aren't approved.
2. Approved template wording in `apps/api/data/message_templates.json`: set `"status": "approved"` only after the team approves the text and the provider approves the template.
3. In **your own environment** (never in the repo):
   - `ALERT_TEST_ALLOWLIST` = your test numbers, comma separated;
   - `ALERTS_ENABLED_GLOBAL=true` for the dry run only;
   - the real keys (`TOKEN_PEPPER`, `PHONE_ENC_KEYS`, `PHONE_HMAC_KEY`, `WHATSAPP_*`, `SMS_*`, `BACKUP_ENC_KEY`, `INTERNAL_JOB_SECRET`).

## Dry run
1. Sign up each test phone: message the WhatsApp number "HI" and follow the steps (PIN, YES, language, level).
2. Run `python scripts/dry_run_alerts.py` from the repo root. It sends one test alert to each allow-listed number and to nobody else.
3. Run the evening job on a hot day, or on a test day: `POST /internal/jobs/evening_alerts`, then `POST /internal/jobs/send_queue` with the `X-Job-Secret` header.

## Checklist

| Check | How | Automated evidence | Result |
|---|---|---|---|
| STOP works | Reply STOP from a test phone | `tests/test_p2_whatsapp_otp.py::test_full_whatsapp_sign_up_then_stop_deletes`; QA P2-04 | |
| Quiet hours hold (nothing 22:00–06:00 IST) | Queue an alert, run `send_queue` after 22:00 | `tests/test_notify.py::test_evening_alert_queued_once_then_sent_only_when_enabled` | |
| Repeat-day rule (`ALERT_REPEAT_DAYS`) | Three hot days in a row: alert on day 1, on any increase, then every N days | `tests/test_notify.py::test_fatigue_first_day_increase_then_every_n_days` | |
| One alert per day per channel | Run `evening_alerts` twice for the same evening | Same test (second run queues nothing); `notice_log` unique key | |
| No health words in any text | Read every message received on the test phones | `tests/test_notify.py::test_no_health_words_in_any_template_or_alert_text`; QA P2-18 | |
| A backup restore works | `POST /internal/jobs/backup`, then `python -m app.backup restore <file> <new.db>` and open it | `tests/test_p2_secure_db.py::test_backup_and_restore`; QA P2-14 | |
| Only allow-listed numbers receive anything | Sign up one phone that isn't on the list; run the dry run | `tests/test_notify.py::test_allowlist_holds_everyone_else` | |
| Kill switch | Unset `ALERTS_ENABLED_GLOBAL`; run `send_queue` | QA P2-12 | |

## Sign-off

| Reviewer | Date | Decision (go / fix first) | Notes |
|---|---|---|---|
| | | | |
