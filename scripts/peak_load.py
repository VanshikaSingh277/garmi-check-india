"""Load test at peak-evening traffic (spec §10.4 from Phase 7) against a RUNNING server you own.

The evening peak is when alerts go out (18:00-21:00 IST) and families open the app. The default mix below is a design
choice, not a measured figure (TEAM_TODO: expected users at launch):
  - 60% saved homes asking for their status (POST /api/v1/households/me/status, one token per simulated home)
  - 25% one-off status checks (POST /api/status/individual) for a handful of cities
  - 15% light reads (/api/health, /api/v1/gov/today)
Weather comes from a few cells only, so the test measures our server, not the weather provider.

Start the server with HOUSEHOLDS_ENABLED=true and a high RATE_STATELESS_PER_MIN (one machine looks like one IP), then:
    python scripts/peak_load.py [base_url] [--users 50] [--seconds 60] [--homes 40] [--out docs/launch/load_test_results.md]
Pass/fail: no 5xx, under 1% errors, p95 under 1.5 s (both design choices, see TEAM_TODO).
"""
import random
import statistics
import sys
import threading
import time
from urllib.parse import urlparse

import httpx


def opt(name, default):
    return type(default)(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name and i + 1 < len(sys.argv)), default))


args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and not sys.argv[i - 1].startswith("--")]
BASE = args[0] if args else "http://localhost:8000"
USERS, SECONDS, HOMES, OUT = opt("--users", 50), opt("--seconds", 60), opt("--homes", 40), opt("--out", "")
P95_LIMIT_S, ERROR_LIMIT = 1.5, 0.01
if urlparse(BASE).hostname not in ("localhost", "127.0.0.1") and "--i-own-this-host" not in sys.argv:
    sys.exit(f"Refusing {BASE}: only localhost unless you pass --i-own-this-host (and the host is yours).")

CITIES = [(28.61, 77.21), (26.91, 75.79), (13.08, 80.27), (23.02, 72.57), (21.15, 79.09)]   # Delhi, Jaipur, Chennai, Ahmedabad, Nagpur
STATUS = {"roof": "rcc_brick_top", "vulnerable": [], "devices": {"fan": True, "cooler": False, "ac": False},
          "roof_access": True, "cross_ventilation": False, "budget": "low", "lang": "en"}


def new_home(c, lat, lon) -> str:
    body = {"consent": {"version": "draft-1", "accepted": True}, "lang": "en", "place": {"lat": lat, "lon": lon},
            "home": {"roof": "rcc_brick_top", "fan": True}, "summary": {"higher_risk": False}, "alerts": {"enabled": False}}
    r = c.post("/api/v1/households", json=body)
    r.raise_for_status()
    return r.json()["token"]


setup = httpx.Client(base_url=BASE, timeout=60)
tokens = [new_home(setup, *CITIES[i % len(CITIES)]) for i in range(HOMES)]
for lat, lon in CITIES:                                     # warm the weather cache once per cell
    setup.post("/api/status/individual", json={**STATUS, "lat": lat, "lon": lon}).raise_for_status()

samples: list[tuple[str, int, float]] = []
lock = threading.Lock()
stop_at = time.monotonic() + SECONDS


def user(n: int):
    rnd = random.Random(n)
    c = httpx.Client(base_url=BASE, timeout=30)
    while time.monotonic() < stop_at:
        pick = rnd.random()
        t0 = time.perf_counter()
        try:
            if pick < 0.60:
                kind = "saved home status"
                r = c.post("/api/v1/households/me/status", json={}, headers={"Authorization": "Bearer " + rnd.choice(tokens)})
            elif pick < 0.85:
                kind = "one-off status"
                lat, lon = rnd.choice(CITIES)
                r = c.post("/api/status/individual", json={**STATUS, "lat": lat, "lon": lon})
            else:
                kind = "light read"
                r = c.get(rnd.choice(["/api/health", "/api/v1/gov/today"]))
            code = r.status_code
        except httpx.HTTPError:
            code = 0
        with lock:
            samples.append((kind, code, time.perf_counter() - t0))
        time.sleep(rnd.uniform(0.2, 1.0))                  # a person, not a tight loop


threads = [threading.Thread(target=user, args=(i,)) for i in range(USERS)]
started = time.monotonic()
for t in threads:
    t.start()
for t in threads:
    t.join()
elapsed = time.monotonic() - started


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else 0.0


rows = []
for kind in ("saved home status", "one-off status", "light read", "all"):
    s = [x for x in samples if kind == "all" or x[0] == kind]
    t = [x[2] for x in s]
    errs = sum(1 for x in s if x[1] == 0 or x[1] >= 400)
    rows.append((kind, len(s), errs, statistics.median(t) if t else 0, pct(t, 95), pct(t, 99), max(t) if t else 0))
total = rows[-1]
fivexx = sum(1 for x in samples if x[1] >= 500 or x[1] == 0)
ok = fivexx == 0 and total[2] <= ERROR_LIMIT * max(1, total[1]) and total[4] <= P95_LIMIT_S
codes = sorted({x[1] for x in samples})
lines = ["# Load test results", "",
         f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE}: {USERS} simulated people for {elapsed:.0f} s, {HOMES} saved homes,"
         f" {len(CITIES)} weather cells. {total[1] / elapsed:.1f} requests/s. Status codes seen: {codes}.", "",
         "| Request | Count | Errors | p50 s | p95 s | p99 s | max s |", "|---|---|---|---|---|---|---|"]
lines += [f"| {k} | {n} | {e} | {p50:.3f} | {p95:.3f} | {p99:.3f} | {mx:.3f} |" for k, n, e, p50, p95, p99, mx in rows]
lines += ["", f"Limits (design choices): no 5xx, errors ≤ {ERROR_LIMIT:.0%}, p95 ≤ {P95_LIMIT_S} s.",
          f"**{'PASS' if ok else 'FAIL'}** (5xx or no answer: {fivexx}).", ""]
report = "\n".join(lines)
if OUT:
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(report)
print(report)
sys.exit(0 if ok else 1)
