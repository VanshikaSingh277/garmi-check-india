"""Settings from the environment (names in env.example). Security and ops limits live here, not in
verified_numbers.csv (spec §2 rule 2)."""
import ipaddress
import os


def _list(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


def _int(name: str, default: int | None) -> int | None:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


def _int_d(name: str, default: int) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


ENV = os.environ.get("ENV", "dev").strip().lower()
PROD = ENV == "prod"
DOCS_ENABLED = os.environ.get("DOCS_ENABLED", "").strip().lower() == "true"

# CORS: the Capacitor apps' origins always; http://localhost only in dev (spec §8.5)
APP_ORIGINS = ["capacitor://localhost", "https://localhost"] + ([] if PROD else ["http://localhost"])
ORIGINS = APP_ORIGINS + _list("THANDAK_ORIGINS")
ALLOWED_HOSTS = _list("ALLOWED_HOSTS") or ([] if PROD else ["localhost", "127.0.0.1", "testserver"])
TRUSTED_PROXIES = [ipaddress.ip_network(c, strict=False) for c in _list("TRUSTED_PROXY_CIDRS")]
LOG_HASH_SECRET = os.environ.get("LOG_HASH_SECRET", "")

# request limits (spec §6.1) and rate limits (spec §8.7)
MAX_BODY_BYTES = 16 * 1024
RATE_STATELESS_PER_MIN = _int_d("RATE_STATELESS_PER_MIN", 300)     # per IP; tune with metrics (spec §8.7)
RATE_BAD_TOKEN_PER_MIN = 30     # unknown or expired tokens per IP; requests with a token skip the IP limit (CGNAT, spec §8.7)

# weather (spec §4)
WEATHER_PROVIDER = os.environ.get("WEATHER_PROVIDER", "open-meteo").strip().lower()
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
WEATHER_DAILY_BUDGET = _int("WEATHER_DAILY_BUDGET", None)   # None: no budget check

# room estimate (spec §7.4)
ROOM_MODEL_MODE = os.environ.get("ROOM_MODEL_MODE", "validated_only").strip().lower()
if ROOM_MODEL_MODE not in ("validated_only", "rough_guide"):
    raise RuntimeError("ROOM_MODEL_MODE must be validated_only or rough_guide")

# runtime state that must not live in the read-only data/ folder (spec §4, §8.9)
STATE_DIR = os.environ.get("THANDAK_STATE_DIR", os.path.join(os.path.dirname(__file__), "..", ".cache"))

# ------------------------------------------------------------------ Phase 2: database, phones, alerts (spec §4, §5, §6.5-6.6, §7.6)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or "sqlite:///" + os.path.abspath(os.path.join(STATE_DIR, "thandak.db")).replace("\\", "/")
TOKEN_PEPPER = os.environ.get("TOKEN_PEPPER", "")
PHONE_ENC_KEYS = os.environ.get("PHONE_ENC_KEYS", "")       # "id:base64key,id2:base64key2" - the first one encrypts
PHONE_HMAC_KEY = os.environ.get("PHONE_HMAC_KEY", "")
INTERNAL_JOB_SECRET = os.environ.get("INTERNAL_JOB_SECRET", "")
WHATSAPP_WEBHOOK_SECRET = os.environ.get("WHATSAPP_WEBHOOK_SECRET", "")
SMS_WEBHOOK_SECRET = os.environ.get("SMS_WEBHOOK_SECRET", "")
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "fake").strip().lower()
WHATSAPP_PROVIDER = os.environ.get("WHATSAPP_PROVIDER", "fake").strip().lower()
OTP_DAILY_CAP = _int_d("OTP_DAILY_CAP", 500)
RETENTION_DAYS_INACTIVE = _int_d("RETENTION_DAYS_INACTIVE", 365)
ALERT_REPEAT_DAYS = _int_d("ALERT_REPEAT_DAYS", 3)
ALERTS_ENABLED_GLOBAL = os.environ.get("ALERTS_ENABLED_GLOBAL", "").strip().lower() == "true"   # off by default
ALERT_TEST_ALLOWLIST = _list("ALERT_TEST_ALLOWLIST")          # phone numbers; set only in your own environment
BACKUP_DIR = os.environ.get("BACKUP_DIR", "").strip() or os.path.join(STATE_DIR, "backups")
BACKUP_ENC_KEY = os.environ.get("BACKUP_ENC_KEY", "")         # base64, 32 bytes
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

# security and ops limits (config, not verified_numbers.csv: spec §2 rule 2)
OTP_TTL_MIN = 10
OTP_MAX_ATTEMPTS = 5
OTP_PER_PHONE_HOUR, OTP_PER_PHONE_DAY, OTP_PER_IP_DAY = 3, 10, 30
SMS_PROOF_TTL_MIN = 15
PUSH_TEST_PER_DAY = 3
TARGET_MAX_FAILS = 5
QUIET_START_H, QUIET_END_H = 22, 6           # nothing is sent 22:00-06:00 IST (spec §7.6)
WA_WINDOW_S = 300                            # webhooks older than 5 minutes are rejected (spec §6.5)
BACKUP_KEEP_DAYS = 14


def missing(*names: str) -> list[str]:
    """Which of these secrets are not set (features that need them answer 503 instead of running half-configured)."""
    return [n for n in names if not globals().get(n)]

# ------------------------------------------------------------------ Phase 4: saved households and app push (spec §6.3, §6.5)
# Off until the frontend prerequisite in spec §6.3 is done (escape-by-default templating + token in Keychain/Keystore)
HOUSEHOLDS_ENABLED = os.environ.get("HOUSEHOLDS_ENABLED", "").strip().lower() == "true"
HOUSEHOLDS_PER_IP_HOUR = 60
HOUSEHOLDS_DAILY_CAP = _int_d("HOUSEHOLDS_DAILY_CAP", 5000)
FCM_CREDENTIALS_JSON = os.environ.get("FCM_CREDENTIALS_JSON", "")      # a service-account JSON, or a path to one
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")            # base64url raw P-256 private key
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")                    # mailto: or https: contact
CONSENT_VERSION_APP = os.environ.get("CONSENT_VERSION_APP", "draft-1")

# ------------------------------------------------------------------ Phase 5: assisted mode (spec §5.10, §6.7)
PERSON_ENC_KEYS = os.environ.get("PERSON_ENC_KEYS", "")       # "id:base64key,..." - the first one encrypts
WORKER_SESSION_DAYS = 30
ADMIN_SESSION_HOURS = 12
CONSENT_SCRIPT_VERSION = os.environ.get("CONSENT_SCRIPT_VERSION", "draft-1")

# ------------------------------------------------------------------ Phase 6: readings, IMD, government numbers (spec §6.4, §6.8, §7.1, §7.4)
IMD_ENABLED = os.environ.get("IMD_ENABLED", "").strip().lower() == "true"     # off until IMD onboarding and a real adapter
IMD_API_BASE = os.environ.get("IMD_API_BASE", "")
IMD_API_KEY = os.environ.get("IMD_API_KEY", "")
AGG_MIN_COUNT = _int_d("AGG_MIN_COUNT", 10)
READING_MIN_C, READING_MAX_C = 10.0, 55.0
CALIBRATION_WINDOW_DAYS = 30
