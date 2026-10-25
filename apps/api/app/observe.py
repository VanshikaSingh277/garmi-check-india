"""Errors and metrics (spec §4, §8.8). Sentry only when SENTRY_DSN is set, with send_default_pii=False and a scrubber
that removes Authorization headers, cookies, bodies, query strings, and anything shaped like a phone number, a token
or a coordinate pair. Request counters feed /internal/metrics."""
import logging
import re
from typing import Any, cast
import threading
from collections import Counter

from . import config

PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
TOKEN = re.compile(r"[A-Za-z0-9_\-]{32,}")
COORD = re.compile(r"-?\d{1,2}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")
SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-job-secret", "x-thandak-signature"}

log = logging.getLogger("thandak")
_lock = threading.Lock()
requests: Counter[str] = Counter()


def count(status: int, ms: float):
    with _lock:
        requests[f"{status // 100}xx"] += 1
        requests["total"] += 1
        requests["ms_total"] += int(ms)


def snapshot() -> dict:
    with _lock:
        r = dict(requests)
    n = r.get("total", 0)
    return {"requests": {k: v for k, v in r.items() if k != "ms_total"}, "mean_ms": round(r.get("ms_total", 0) / n, 1) if n else None}


def _clean(v):
    if isinstance(v, str):
        return COORD.sub("[coords]", TOKEN.sub("[token]", PHONE.sub("[phone]", v)))
    if isinstance(v, dict):
        return {k: ("[removed]" if str(k).lower() in SECRET_HEADERS else _clean(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def scrub(event: dict, _hint=None) -> dict:
    req = event.get("request")
    if isinstance(req, dict):
        for k in ("data", "cookies", "query_string", "env"):
            req.pop(k, None)
        if "url" in req:
            req["url"] = str(req["url"]).split("?")[0]
        if isinstance(req.get("headers"), dict):
            req["headers"] = {k: v for k, v in req["headers"].items() if k.lower() not in SECRET_HEADERS}
    event.pop("user", None)
    return _clean(event)


def init_sentry():
    if not config.SENTRY_DSN:
        return False
    import sentry_sdk
    sentry_sdk.init(dsn=config.SENTRY_DSN, send_default_pii=False, before_send=cast(Any, scrub),
                    before_breadcrumb=cast(Any, lambda crumb, _h: _clean(crumb)), traces_sample_rate=0.0, environment=config.ENV)
    return True
