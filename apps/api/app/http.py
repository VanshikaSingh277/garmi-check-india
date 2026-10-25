"""HTTP hardening (spec §6.1, §8.5-8.7): request size and type limits, per-IP rate limit, security headers, and one JSON
access-log line per request that never holds query strings, bodies, tokens, phone numbers or coordinates."""
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import sys
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone

from . import config, observe

log = logging.getLogger("thandak.access")
if not log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

JSON_TYPES = ("application/json",)
API_CSP = "default-src 'none'; frame-ancestors 'none'"
COMMON = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
          (b"permissions-policy", b"geolocation=(self), camera=(), microphone=(), payment=(), usb=()"),
          (b"x-frame-options", b"DENY")]
if config.PROD:
    COMMON.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))


def site_csp(index_html: str | None) -> str:
    """The website's CSP. Inline scripts in index.html (the dark-mode script) are allowed by hash, so no 'unsafe-inline'
    for scripts; styles need it because the views set style attributes. MapLibre needs blob: workers and the tile host."""
    hashes = []
    for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", index_html or "", flags=re.S):
        hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'")
    tiles = "https://tile.openstreetmap.org"
    return ("default-src 'self'; script-src 'self' " + " ".join(hashes) + "; style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data: blob: {tiles}; connect-src 'self' {tiles}; worker-src 'self' blob:; font-src 'self' data:; "
            "manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def client_ip(scope) -> str:
    """The caller's IP. X-Forwarded-For is trusted only when the direct peer is one of TRUSTED_PROXY_CIDRS (spec §8.7)."""
    peer = (scope.get("client") or ("unknown", 0))[0]

    def trusted(ip: str) -> bool:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(a in n for n in config.TRUSTED_PROXIES)
    if not trusted(peer):
        return peer
    xff = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"x-forwarded-for"), "")
    for hop in reversed([h.strip() for h in xff.split(",") if h.strip()]):
        if not trusted(hop):
            return hop
    return peer


def ip_tag(ip: str) -> str:
    """A truncated HMAC of the IP with a key that changes every UTC day (spec §8.6). Without LOG_HASH_SECRET: nothing."""
    if not config.LOG_HASH_SECRET:
        return "-"
    day_key = hmac.new(config.LOG_HASH_SECRET.encode(), datetime.now(timezone.utc).strftime("%Y-%m-%d").encode(), hashlib.sha256).digest()
    return hmac.new(day_key, ip.encode(), hashlib.sha256).hexdigest()[:12]


class RateLimiter:
    """Sliding one-minute window per key, in process (Redis once there is more than one server, spec §4)."""

    def __init__(self, limit: int, window_s: float = 60.0, max_keys: int = 100_000):
        self.limit, self.window, self.max_keys = limit, window_s, max_keys
        self._hits: OrderedDict[str, deque] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            q = self._hits.pop(key, None) or deque()
            while q and now - q[0] >= self.window:
                q.popleft()
            ok = len(q) < self.limit
            if ok:
                q.append(now)
            self._hits[key] = q
            while len(self._hits) > self.max_keys:
                self._hits.popitem(last=False)
            retry = 0 if ok else max(1, int(self.window - (now - q[0])) + 1)
        return ok, retry

    def blocked(self, key: str) -> bool:
        """True when the key is at its limit, without counting a hit."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key) or deque()
            return sum(1 for t in q if now - t < self.window) >= self.limit


BAD_TOKENS = RateLimiter(config.RATE_BAD_TOKEN_PER_MIN)


def token_failed(request) -> None:
    """Count an unknown or expired token against the caller's IP, so made-up tokens can't dodge the IP limit."""
    BAD_TOKENS.check("ip:" + client_ip(request.scope))


def _json(status: int, code: str, message: str, extra_headers=()) -> tuple[dict, dict]:
    body = json.dumps({"error": code, "message": message}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())] + list(extra_headers)
    return {"type": "http.response.start", "status": status, "headers": headers}, {"type": "http.response.body", "body": body}


class Guard:
    """Outermost ASGI middleware: limits first, then headers and the access log on the way out."""

    def __init__(self, app, site_csp_value: str, limiter: RateLimiter | None = None):
        self.app, self.site_csp = app, site_csp_value.encode()
        self.limiter = limiter or RateLimiter(config.RATE_STATELESS_PER_MIN)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0, path, method = time.perf_counter(), scope["path"], scope["method"]
        api = path.startswith("/api/")
        status = {"code": 500}

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"server"]
                headers += COMMON + [(b"content-security-policy", API_CSP.encode() if api else self.site_csp)]
                message = {**message, "headers": headers}
            await send(message)

        async def reply(start, body):
            await send_wrapped(start)
            await send_wrapped(body)

        try:
            if api:
                hdr = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
                ip = "ip:" + client_ip(scope)
                # requests with a token are limited per token in the route (120/min), not per IP: many homes share one
                # carrier IP behind CGNAT. Too many bad tokens from one IP puts it back under a limit.
                if hdr.get("authorization", "").startswith("Bearer "):
                    ok, retry = not BAD_TOKENS.blocked(ip), 60
                else:
                    ok, retry = self.limiter.check(ip)
                if not ok:
                    return await reply(*_json(429, "rate_limited", "Too many requests", [(b"retry-after", str(retry).encode())]))
                if method in ("POST", "PUT", "PATCH"):
                    ctype = hdr.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in JSON_TYPES:
                        return await reply(*_json(415, "unsupported_media_type", "Send JSON"))
                    if hdr.get("content-length", "").isdigit() and int(hdr["content-length"]) > config.MAX_BODY_BYTES:
                        return await reply(*_json(413, "too_large", "Request body too large"))
                    body, more = b"", True
                    while more:                                   # a body without Content-Length is counted as it arrives
                        msg = await receive()
                        body += msg.get("body", b"")
                        more = msg.get("more_body", False)
                        if len(body) > config.MAX_BODY_BYTES:
                            return await reply(*_json(413, "too_large", "Request body too large"))
                    sent = {"done": False}

                    async def receive_buffered():
                        if sent["done"]:
                            return {"type": "http.disconnect"}
                        sent["done"] = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await self.app(scope, receive_buffered, send_wrapped)
            return await self.app(scope, receive, send_wrapped)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or ("unmatched" if api else "static")
            observe.count(status["code"], (time.perf_counter() - t0) * 1000)
            log.info(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "m": method, "route": template,
                                 "s": status["code"], "ms": round((time.perf_counter() - t0) * 1000, 1),
                                 "ip": ip_tag(client_ip(scope))}, separators=(",", ":")))
