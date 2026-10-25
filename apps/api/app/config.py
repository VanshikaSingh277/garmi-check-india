"""Settings from the environment (names in env.example). Security and ops limits live here, not in
verified_numbers.csv (spec §2 rule 2)."""
import ipaddress
import os


def _list(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


def _int(name: str, default: int | None) -> int | None:
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
RATE_STATELESS_PER_MIN = 300

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
