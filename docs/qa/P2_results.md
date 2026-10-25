# Phase 2 test results

Run 2026-10-25 15:45 against http://localhost:8000 with test secrets and a throwaway database.

| ID | Title | Result | Notes |
|---|---|---|---|
| P2-01 | WhatsApp sign-up | PASS | replies=['ask_pin', 'consent', 'ask_lang', 'ask_level', 'signed_up']; home=[(26.9, 75.8, 'Jaipur')] |
| P2-02 | Hindi sign-up | PASS | replies=['ask_pin', 'consent', 'ask_lang', 'ask_level', 'signed_up']; last reply: हो गया। Jaipur में गर्म दिन से एक शाम पहले आपको गर्मी का अलर |
| P2-03 | HELP and ALERT | PASS | help, alert_now; help mentions 112: True |
| P2-04 | STOP deletes the home | PASS | reply=stop_deleted; household left=0; events=['deleted', 'given', 'withdrawn'] |
| P2-05 | Unsigned, old or forged webhook | PASS | [401, 401, 401] |
| P2-06 | Repeated message id | PASS | first={'ok': True, 'reply': 'ask_pin'}; second={'ok': True, 'duplicate': True} |
| P2-07 | OTP send and limits | PASS | [200, 200, 200, 429]; code in a reply: False |
| P2-08 | OTP attempts | PASS | wrong: [400, 400, 400, 400, 400]; right code after 5 wrong: 400 |
| P2-09 | Only Indian mobiles | PASS | 422 {"error":"invalid_phone","message":"Indian mobile numbers (+91) only"} |
| P2-10 | SMS target needs OTP proof | PASS | forged proof 403; real proof 201 |
| P2-11 | Internal routes need the secret | PASS | [403, 403, 200] |
| P2-12 | Kill switch | PASS | {"ran": true, "sent": 0, "failed": 0, "held": 0, "expired": 0, "reason": "ALERTS_ENABLED_GLOBAL is off"} |
| P2-13 | Jobs run once at a time | PASS | ran=[True, True] (True,True means they ran one after the other) |
| P2-14 | Backup and restore | PASS | backup thandak-20261025-101513.db.enc; restored households: 60 |
| P2-15 | Outbox and logs hold no phone numbers | PASS | numbers found: 0; server log checked: True |
| P2-16 | Health shows the database | PASS | db_ok=True |
| P2-17 | Migrations up and down | PASS | exit codes [0, 0, 0] |
| P2-18 | No health words in messages | PASS | 1 passed, 1 warning in 1.51s |
| P2-19 | Alert rules | PASS | 9 passed, 1 warning in 2.13s |

**19 of 19 passed.**
