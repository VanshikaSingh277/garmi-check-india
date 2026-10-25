"""Phase 2 gate dry run (docs/launch/GATE_P2_dry_run.md): queue and send one test alert to each number in
ALERT_TEST_ALLOWLIST only. The numbers must already be signed up (WhatsApp: message the bot; SMS: OTP in the app).
Set ALERT_TEST_ALLOWLIST and ALERTS_ENABLED_GLOBAL=true in your own environment; this script never adds numbers.

Usage (repo root):  python scripts/dry_run_alerts.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from sqlalchemy import select  # noqa: E402

from app import config, db, jobs, messaging, notify, secure  # noqa: E402
from app.models import Household, PushTarget  # noqa: E402

if not config.ALERT_TEST_ALLOWLIST:
    sys.exit("ALERT_TEST_ALLOWLIST is empty: set it to your test numbers (comma separated) in your own environment")
if not config.ALERTS_ENABLED_GLOBAL:
    sys.exit("ALERTS_ENABLED_GLOBAL is off: set ALERTS_ENABLED_GLOBAL=true for the dry run only")
db.migrate()
queued = 0
with db.session() as s:
    for raw in config.ALERT_TEST_ALLOWLIST:
        phone = secure.normalise_phone(raw)
        if not phone:
            print("skipped: not an Indian mobile number")
            continue
        targets = s.scalars(select(PushTarget).where(PushTarget.phone_hmac == secure.phone_hmac(phone), PushTarget.active.is_(True))).all()
        if not targets:
            print(f"number ending {phone[-2:]}: not signed up yet (message the WhatsApp bot or add SMS in the app first)")
        for t in targets:
            h = s.get(Household, t.household_id)
            queued += notify.queue(s, h, t, db.utcnow().date(), "test", None, "test_alert", messaging.render("test_alert", h.lang))
print("queued", queued)
print("send:", jobs.run("send_queue"))
