"""Attack smoke test (spec §8.1, §10.4 from Phase 7): hostile requests against a RUNNING server. Every check must hold:
no 500s, nothing echoed back, the right 4xx, security headers on every answer, the rate limit last.

Only for servers you run yourself. By default it refuses any host but localhost; pass --i-own-this-host for your own
staging host. It never sends an OTP or a message, and needs no secrets.

    python scripts/attack_smoke.py [base_url] [--i-own-this-host] [--out docs/launch/attack_smoke_results.md]
"""
import json
import sys
import time
from urllib.parse import urlparse

import httpx

args = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = args[0] if args else "http://localhost:8000"
OUT = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--out" and i + 1 < len(sys.argv)), None)
if urlparse(BASE).hostname not in ("localhost", "127.0.0.1") and "--i-own-this-host" not in sys.argv:
    sys.exit(f"Refusing {BASE}: only localhost unless you pass --i-own-this-host (and the host is yours).")

c = httpx.Client(base_url=BASE, timeout=30)
MARK = "zz<script>alert(1)</script>zz"
STATUS = {"lat": 28.61, "lon": 77.21, "roof": "tin_top", "vulnerable": [], "devices": {"fan": True, "cooler": False, "ac": False},
          "roof_access": True, "cross_ventilation": False, "budget": "low", "lang": "en"}
results: list[tuple[str, bool, str]] = []
seen_500: list[str] = []
NEED_HEADERS = ("x-content-type-options", "referrer-policy", "content-security-policy", "permissions-policy")


def check(name, r: httpx.Response, ok: bool, note: str = ""):
    """Every answer: never a 500, never the hostile marker, no Server header, security headers present."""
    body = r.text
    extra = []
    if r.status_code >= 500:
        seen_500.append(name)
        extra.append(f"got {r.status_code}")
    if MARK in body or "Traceback" in body or 'File "' in body:
        extra.append("echoed input or a stack trace")
    if "server" in r.headers:
        extra.append("Server header present")
    missing = [h for h in NEED_HEADERS if h not in r.headers]
    if missing:
        extra.append("missing " + ", ".join(missing))
    results.append((name, ok and not extra, f"{r.status_code} {note} {'; '.join(extra)}".strip()))


def run(name, method, path, want, **kw):
    r = c.request(method, path, **kw)
    check(name, r, r.status_code in (want if isinstance(want, tuple) else (want,)))
    return r


# malformed and oversized input (never a 500)
run("wrong content type", "POST", "/api/status/individual", 415, content=json.dumps(STATUS), headers={"content-type": "text/plain"})
run("no content type", "POST", "/api/status/individual", 415, content=json.dumps(STATUS))
run("17 KB body", "POST", "/api/status/individual", 413, content=json.dumps({**STATUS, "pad": "x" * 17000}),
    headers={"content-type": "application/json"})
run("broken JSON", "POST", "/api/status/individual", 422, content="{\"lat\": 28.6,", headers={"content-type": "application/json"})
run("JSON that is a list", "POST", "/api/status/individual", 422, json=[1, 2, 3])
run("extra field", "POST", "/api/status/individual", 422, json={**STATUS, "is_admin": True})
run("NaN latitude", "POST", "/api/status/individual", 422, content=json.dumps(STATUS).replace("28.61", "NaN"),
    headers={"content-type": "application/json"})
run("huge number", "POST", "/api/status/individual", 422, content=json.dumps(STATUS).replace("28.61", "1e400"),
    headers={"content-type": "application/json"})
run("hostile string in an enum", "POST", "/api/status/individual", 422, json={**STATUS, "roof": MARK})
run("deep nesting", "POST", "/api/status/individual", 422, content="[" * 5000 + "]" * 5000, headers={"content-type": "application/json"})
run("point outside India", "GET", "/api/outdoor?lat=51.5&lon=-0.12", 422)
run("lat as text", "GET", "/api/outdoor?lat=abc&lon=77", 422)
run("hostile search", "GET", "/api/search", (200, 422), params={"q": MARK + "' OR 1=1 --"})
run("SQL in a search", "GET", "/api/search", (200, 422), params={"q": "Jaipur'; DROP TABLE household; --"})
run("very long query string", "GET", "/api/search", (200, 414, 422), params={"q": "a" * 6000})

# path traversal and static files
for p in ("/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/..%5c..%5cwindows/win.ini", "/static/..%2f..%2fmain.py", "/.env", "/.git/config"):
    r = c.get(p)
    check(f"traversal {p}", r, r.status_code in (200, 400, 404) and "root:" not in r.text and "[core]" not in r.text
          and "TOKEN_PEPPER" not in r.text, "(200 only as the site's index page)")

# docs, internal routes, auth
for p in ("/docs", "/redoc", "/openapi.json"):
    run(f"docs off {p}", "GET", p, 404)
run("metrics without the job secret", "GET", "/internal/metrics", (401, 403, 404))
run("metrics with a wrong secret", "GET", "/internal/metrics", (401, 403, 404), headers={"x-job-secret": "wrong"})
run("job without the secret", "POST", "/internal/jobs/backup", (401, 403, 404), json={})
run("household route without a token", "GET", "/api/v1/households/me", (401, 404))
run("household route with a made-up token", "GET", "/api/v1/households/me", (401, 404), headers={"Authorization": "Bearer " + "A" * 43})
run("worker route with a made-up token", "GET", "/api/v1/workers/me", 401, headers={"Authorization": "Bearer " + "B" * 43})
run("token in the query string is ignored", "GET", "/api/v1/workers/me?token=abc", 401)

# webhooks: unsigned, wrong signature, old timestamp
body = json.dumps({"message_id": "attack-1", "from": "+910000000000", "text": "STOP"})
JSON = {"content-type": "application/json"}
run("unsigned WhatsApp webhook", "POST", "/api/v1/webhooks/whatsapp", 401, content=body, headers=JSON)
run("bad signature", "POST", "/api/v1/webhooks/whatsapp", 401, content=body,
    headers={**JSON, "x-thandak-timestamp": str(int(time.time())), "x-thandak-signature": "sha256=" + "0" * 64})
run("replayed old webhook", "POST", "/api/v1/webhooks/whatsapp", 401, content=body,
    headers={**JSON, "x-thandak-timestamp": str(int(time.time()) - 3600), "x-thandak-signature": "sha256=" + "0" * 64})
run("unsigned SMS status webhook", "POST", "/api/v1/webhooks/sms-status", 401, content=body, headers=JSON)

# headers, hosts, CORS
r = c.get("/api/health", headers={"Host": "evil.example"})
check("unknown Host header", r, r.status_code == 400 or "evil.example" not in r.text, "(400 when ALLOWED_HOSTS is set)")
r = c.get("/api/health", headers={"Origin": "https://evil.example"})
check("CORS from an unknown origin", r, r.headers.get("access-control-allow-origin") not in ("*", "https://evil.example"))
r = c.options("/api/status/individual", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
results.append(("CORS preflight from an unknown origin", r.status_code < 500 and r.headers.get("access-control-allow-origin") is None,
                str(r.status_code)))
r = c.get("/api/health", headers={"X-Forwarded-For": "1.2.3.4"})
check("X-Forwarded-For from an untrusted peer", r, r.status_code == 200)
r = c.request("TRACE", "/api/health")
check("TRACE method", r, r.status_code in (404, 405))

# rate limit last (it holds this IP for a minute): requests without a token share 300/min per IP
codes = []
for _ in range(400):
    codes.append(c.get("/api/health").status_code)
    if codes[-1] == 429:
        break
last = c.get("/api/health")
results.append(("flood without a token reaches 429 with Retry-After", 429 in codes and last.headers.get("retry-after", "").isdigit(),
                f"first 429 after {codes.index(429) + 1 if 429 in codes else 'none'} requests"))

passed = sum(1 for _, ok, _ in results if ok)
lines = [f"| {n} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for n, ok, note in results]
report = "\n".join(["# Attack smoke results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE}.", "",
                    "| Check | Result | Status / notes |", "|---|---|---|", *lines, "",
                    f"**{passed} of {len(results)} passed. Server errors (5xx): {len(seen_500)}.**", ""])
if OUT:
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(report)
print(report)
sys.exit(0 if passed == len(results) else 1)
