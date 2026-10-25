# Phase 2 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type.
Runner: `python tests/qa/p2_qa.py <server-log>` against a server started with **test** secrets and a throwaway database (see "QA setup"). Never use real phone numbers or real keys for these cases; the numbers below are made up.

**QA setup:** set `THANDAK_STATE_DIR` to an empty folder, and set `TOKEN_PEPPER`, `PHONE_ENC_KEYS`, `PHONE_HMAC_KEY`, `INTERNAL_JOB_SECRET`, `WHATSAPP_WEBHOOK_SECRET`, `SMS_WEBHOOK_SECRET` and `BACKUP_ENC_KEY` to test values. Leave `ALERTS_ENABLED_GLOBAL` unset. Start the API (`run_local.py`), and run the runner with the same environment.

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P2-01 | WhatsApp sign-up | QA setup | Send signed webhooks: HI → PIN 302001 → YES → 1 → 1 | Replies ask_pin, consent, ask_lang, ask_level, signed_up; one household with a 0.1° cell and one WhatsApp target | High | Functional |
| P2-02 | Hindi sign-up | QA setup | Same flow, choose 2 (हिंदी) | Later replies in the outbox are in Hindi | High | Hindi/English |
| P2-03 | HELP and ALERT | P2-01 done | Send HELP, ALERT | help (with 112) and today's level for the area | Medium | Functional |
| P2-04 | STOP deletes the home | P2-01 done | Send STOP | stop_deleted; household gone; consent events given, withdrawn, deleted remain | High | Privacy |
| P2-05 | Unsigned, old or forged webhook | — | Post without signature; with a 10-minute-old timestamp; with a wrong secret | 401 each | High | Security |
| P2-06 | Repeated message id | — | Send the same id twice | Second answer `duplicate: true`; one reply in the outbox | High | Security |
| P2-07 | OTP send and limits | QA setup | Send 4 codes to one number within an hour | 3 × 200, then 429 with Retry-After; the code never appears in a reply | High | Security |
| P2-08 | OTP attempts | P2-07 | Verify with a wrong code 5 times, then the right one | 400 each; the code is dead after 5 tries | High | Security |
| P2-09 | Only Indian mobiles | — | OTP for +1 415… | 422 `invalid_phone` | Medium | Negative |
| P2-10 | SMS target needs OTP proof | A saved home with a token | POST /api/v1/push sms with a forged proof; then with a real one | 403, then 201 | High | Security |
| P2-11 | Internal routes need the secret | — | GET /internal/metrics with no / wrong / right secret | 403, 403, 200 | High | Security |
| P2-12 | Kill switch | ALERTS_ENABLED_GLOBAL unset | Run `send_queue` through /internal/jobs | Nothing sent; reason "ALERTS_ENABLED_GLOBAL is off" | High | Functional |
| P2-13 | Jobs run once | — | Call /internal/jobs/retention_purge twice at the same time | One reports `ran: true`, or both run one after the other; never two at once | Medium | Functional |
| P2-14 | Backup and restore | QA setup | /internal/jobs/backup; then `python -m app.backup restore <file> <new.db>` | Encrypted file written; restored copy opens and holds the households | High | Functional |
| P2-15 | Outbox and logs hold no phone numbers | After P2-01..07 | Read `<state>/outbox.jsonl` and the server log | No full phone number anywhere (outbox keeps only the last 2 digits) | High | Privacy |
| P2-16 | Health shows the database | — | GET /api/health | `db_ok: true` | Low | Functional |
| P2-17 | Migrations up and down | Empty folder | `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` | All succeed | Medium | Functional |
| P2-18 | No health words in messages | — | Automated: tests/test_notify.py::test_no_health_words_in_any_template_or_alert_text | Pass | High | Privacy |
| P2-19 | Alert rules | — | Automated: tests/test_notify.py (when to alert, fatigue, quiet hours, one per day per channel, allow-list) | Pass | High | Functional |
