"""Test setup: a throwaway state folder and database, and fixed test-only secrets (never real keys), set before the app
modules read their configuration. Tests never call the internet: weather comes from tests/fixtures."""
import base64
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="thandak-test-")
TEST_ENV = {
    "THANDAK_STATE_DIR": _STATE,
    "DATABASE_URL": "sqlite:///" + os.path.join(_STATE, "test.db").replace("\\", "/"),
    "TOKEN_PEPPER": "test-pepper",
    "PHONE_ENC_KEYS": "k1:" + base64.b64encode(b"\x01" * 32).decode(),
    "PHONE_HMAC_KEY": "test-phone-hmac",
    "INTERNAL_JOB_SECRET": "test-job-secret",
    "WHATSAPP_WEBHOOK_SECRET": "test-wa-secret",
    "SMS_WEBHOOK_SECRET": "test-sms-secret",
    "BACKUP_ENC_KEY": base64.b64encode(b"\x02" * 32).decode(),
    "BACKUP_DIR": os.path.join(_STATE, "backups"),
    "PERSON_ENC_KEYS": "p1:" + base64.b64encode(b"\x04" * 32).decode(),
    # switches and keys at their defaults, whatever the shell running the tests has set
    "ENV": "dev", "HOUSEHOLDS_ENABLED": "", "ALERTS_ENABLED_GLOBAL": "", "ALERT_TEST_ALLOWLIST": "", "SENTRY_DSN": "",
    "VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": "", "VAPID_SUBJECT": "", "FCM_CREDENTIALS_JSON": "", "ROOM_MODEL_MODE": "validated_only",
    "WEATHER_DAILY_BUDGET": "", "DOCS_ENABLED": "", "ALLOWED_HOSTS": "", "THANDAK_ORIGINS": "",
}
for k, v in TEST_ENV.items():
    os.environ[k] = v
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app import db  # noqa: E402

db.migrate()
