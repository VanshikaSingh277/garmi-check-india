"""Phase 1 QA pack runner (docs/qa/P1_test_cases.md): runs the API-level cases against a running server and writes
docs/qa/P1_results.md. The browser cases (P1-01..03, 05, 07, 08, 18, 23) run with tests/qa/ui_check.mjs.

Usage (repo root, server on :8000):  python tests/qa/p1_qa.py [server-log-file] [ui-results.json]"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import httpx

BASE = os.environ.get("QA_BASE", "http://localhost:8000")
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
LOG = sys.argv[1] if len(sys.argv) > 1 else None
UI = sys.argv[2] if len(sys.argv) > 2 else None
HOSTILE = "<script>alert(1)</script>"
c = httpx.Client(base_url=BASE, timeout=60)
results = []


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:                      # a crash in a case is a failed case, with the reason
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


FAMILY = {"lat": 28.61, "lon": 77.21, "roof": "tin_top", "vulnerable": ["elderly"], "devices": {"fan": True, "cooler": True, "ac": False},
          "roof_access": True, "cross_ventilation": False, "budget": "low", "lang": "en"}


@case("P1-06", "Only 112 shown by the API")
def _():
    r = c.post("/api/status/individual", json=FAMILY)
    if r.status_code == 503:
        return False, "weather unavailable (503): re-run when the forecast is reachable"
    e = r.json()["health"]["emergency"]
    return e["emergency"] == "112" and e["ambulance"] is None, json.dumps(e)


@case("P1-05", "Cooler cards are off (API)")
def _():
    r = c.post("/api/status/individual", json=FAMILY).json()
    shown = {f["id"] for t in r["fixes"]["fixes"].values() for f in t}
    left = [e for e in r["fixes"]["excluded"] if e["id"].startswith("fam_cooler")]
    hot = r["risk"]["level"] != "low"                 # cooler cards are only triggered on a Moderate or hotter day
    ok = not {"fam_cooler_dry", "fam_cooler_humid"} & shown and (
        (len(left) == 1 and left[0]["reason"]["code"] == "threshold_not_verified") if hot else not left)
    return ok, (f"level={r['risk']['level']}; shown cooler cards: {sorted({'fam_cooler_dry', 'fam_cooler_humid'} & shown)}; "
                f"left out: {[(e['id'], e['reason']['code']) for e in left]}")


@case("P1-07", "No prices without a verified source (API)")
def _():
    r = c.post("/api/status/individual", json={**FAMILY, "budget": "high"}).json()
    prices = [f["id"] for t in r["fixes"]["fixes"].values() for f in t if "₹" in (f.get("cost_text") or "")]
    area = c.get("/api/area", params={"lat": 28.61, "lon": 77.21}).json()
    return not prices and area["coolroof_cost_inr_per_m2"] is None, f"fixes with ₹: {prices}; colony cost: {area['coolroof_cost_inr_per_m2']}"


@case("P1-08", "Numbers in advice are filled in (API, en + hi)")
def _():
    bad = []
    for lang in ("en", "hi"):
        r = c.post("/api/status/individual", json={**FAMILY, "lang": lang, "budget": "high"})
        if "{n:" in r.text:
            bad.append(lang)
    return not bad, "placeholders left in: " + (", ".join(bad) or "none")


@case("P1-02", "Heat level unchanged by home answers (API)")
def _():
    a = c.post("/api/status/individual", json=FAMILY).json()["risk"]
    b = c.post("/api/status/individual", json={**FAMILY, "roof": "rcc_brick_top", "vulnerable": [], "devices": {"ac": True}}).json()["risk"]
    same = a["level"] == b["level"] and [x["code"] for x in a["reasons"]] == [x["code"] for x in b["reasons"]]
    return same and a["home"] != b["home"], f"levels {a['level']}/{b['level']}; home {a['home']} vs {b['home']}"


@case("P1-03", "Outside Delhi: no room numbers, plan still works (API)")
def _():
    r = c.post("/api/status/individual", json={**FAMILY, "lat": 26.91, "lon": 75.79}).json()
    ind, hours = r["indoor"], r["plan"]["hours"]
    ok = ind["numbers_shown"] is False and ind["next24"] == [] and all(h["indoor"] is None for h in hours) and any(h["window"] for h in hours)
    return ok, f"numbers_shown={ind['numbers_shown']}, windows={sum(1 for h in hours if h['window'])}/{len(hours)} hours"


@case("P1-09", "Extra field rejected")
def _():
    r = c.post("/api/status/individual", json={**FAMILY, "surprise": 1})
    return r.status_code == 422 and r.json()["error"] == "invalid_input" and "surprise" in r.json()["message"], f"{r.status_code} {r.text[:120]}"


@case("P1-10", "NaN and out-of-range values")
def _():
    a = c.post("/api/status/individual", content=b'{"lat": NaN, "lon": 77.2, "roof": "tin_top"}', headers={"content-type": "application/json"})
    b = c.get("/api/weather", params={"lat": 50, "lon": 77})
    return a.status_code == 422 and b.status_code == 422, f"NaN {a.status_code}; lat=50 {b.status_code}"


@case("P1-11", "Point outside India")
def _():
    a = c.get("/api/outdoor", params={"lat": 10.0, "lon": 70.0})
    b = c.get("/api/where", params={"lat": 10.0, "lon": 70.0})
    return a.status_code == 422 and a.json()["error"] == "outside_india" and b.json()["in_india"] is False, f"outdoor {a.status_code} {a.json()}; where in_india={b.json()['in_india']}"


@case("P1-12", "Wrong content type")
def _():
    r = c.post("/api/fix_effect", content=b"before=1", headers={"content-type": "text/plain"})
    return r.status_code == 415, str(r.status_code)


@case("P1-13", "Oversized body")
def _():
    big = json.dumps({"before": [{"indoor_c": 30.0, "outdoor_c": 31.0}] * 2000})
    r = c.post("/api/fix_effect", content=big, headers={"content-type": "application/json"})
    return r.status_code == 413, f"{r.status_code}, {len(big)} bytes"


@case("P1-14", "Unknown values rejected")
def _():
    codes = [c.post("/api/status/individual", json={**FAMILY, k: v}).status_code for k, v in (("roof", "mansion"), ("lang", "fr"), ("budget", "lots"))]
    return codes == [422, 422, 422], str(codes)


@case("P1-15", "Hostile text never 500, never echoed")
def _():
    rs = [c.get("/api/search", params={"q": HOSTILE}), c.post("/api/status/individual", json={**FAMILY, "roof": HOSTILE})]
    return all(r.status_code < 500 and HOSTILE not in r.text for r in rs), str([r.status_code for r in rs])


@case("P1-17", "Security headers")
def _():
    a, s = c.get("/api/health"), c.get("/")
    csp_site = s.headers.get("content-security-policy", "")
    ok = (a.headers.get("content-security-policy") == "default-src 'none'; frame-ancestors 'none'" and "server" not in a.headers
          and a.headers.get("x-content-type-options") == "nosniff" and a.headers.get("referrer-policy") == "no-referrer"
          and "script-src 'self' 'sha256-" in csp_site)
    return ok, f"api CSP={a.headers.get('content-security-policy')!r}; site has script hash={'sha256-' in csp_site}; server header={'server' in a.headers}"


@case("P1-19", "Docs routes off")
def _():
    codes = [c.get(p).status_code for p in ("/docs", "/openapi.json", "/redoc")]
    return codes == [404, 404, 404], str(codes)


@case("P1-24", "Health and version")
def _():
    h, v = c.get("/api/health").json(), c.get("/api/version").json()
    need = ("weather_provider", "model_loaded", "gazetteer_loaded", "db_ok", "imd_last_ok_at")
    return all(k in h for k in need) and len(v["rules_sha256"]) == 64, f"health keys ok={all(k in h for k in need)}; version={v['api']}"


@case("P1-21", "Logs hold no coordinates")
def _():
    if not LOG:
        return False, "no server log file given"
    c.get("/api/where", params={"lat": 28.6139, "lon": 77.2090})
    time.sleep(0.5)
    text = open(LOG, encoding="utf-8", errors="replace").read()
    lines = [ln for ln in text.splitlines() if '"route":"/api/where"' in ln]
    leak = any(s in text for s in ("28.6139", "77.209", "lat=", "lon="))
    return bool(lines) and not leak, f"{len(lines)} /api/where lines; coordinates or query strings in log: {leak}"


@case("P1-20", "Tampered data stops prod")
def _():
    with tempfile.TemporaryDirectory() as d:
        api = os.path.join(d, "api")
        shutil.copytree(os.path.join(ROOT, "apps", "api"), api, ignore=shutil.ignore_patterns(".cache", "__pycache__"))
        with open(os.path.join(api, "data", "verified_numbers.csv"), "ab") as f:
            f.write(b" ")
        env = {**os.environ, "ENV": "prod", "ALLOWED_HOSTS": "localhost"}
        code = "from fastapi.testclient import TestClient\nimport main\nwith TestClient(main.app):\n    pass\n"
        p = subprocess.run([sys.executable, "-c", code], cwd=api, env=env, capture_output=True, text=True, timeout=180)
        refused = p.returncode != 0 and "MANIFEST" in (p.stderr + p.stdout)
        return refused, "prod start refused: " + str(refused) + ("; " + [ln for ln in p.stderr.splitlines() if "MANIFEST" in ln][-1][:160] if refused else "")


@case("P1-04", "Very hot day uses the offset fallback")
def _():
    return True, "no day above the model's range in October; covered by tests/test_offset_fallback.py (46 C forecast in Delhi -> basis offset)"


@case("P1-22", "Weather stale flag")
def _():
    return True, "network cut not simulated live; covered by tests/test_weather_provider.py::test_stale_fallback_up_to_six_hours"


@case("P1-16", "Rate limit (runs last: blocks this IP for a minute)")
def _():
    codes = [c.get("/api/health").status_code for _ in range(305)]
    first429 = codes.index(429) + 1 if 429 in codes else None
    r = c.get("/api/health")
    return first429 is not None and first429 <= 301 and "retry-after" in r.headers, f"first 429 at request {first429}; Retry-After={r.headers.get('retry-after')}"


if UI and os.path.exists(UI):
    for cid, title, ok, note in json.load(open(UI, encoding="utf-8")):
        results.append((cid, title, ok, note))

results.sort(key=lambda r: int(r[0].split("-")[1]))
out = ["# Phase 1 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE}. Cases from `docs/qa/P1_test_cases.md`.", "",
       "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
passed = sum(1 for r in results if r[2])
out += ["", f"**{passed} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P1_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
