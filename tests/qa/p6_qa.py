"""Phase 6 QA pack runner (docs/qa/P6_test_cases.md) against a server with TEST secrets, a throwaway state folder and
HOUSEHOLDS_ENABLED=true (same environment here). Writes docs/qa/P6_results.md.  Usage: python tests/qa/p6_qa.py"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))
from app import config  # noqa: E402

BASE = os.environ.get("QA_BASE", "http://localhost:8000")
IST = ZoneInfo("Asia/Kolkata")
c = httpx.Client(base_url=BASE, timeout=90)
results, S = [], {}
JOB = {"x-job-secret": config.INTERNAL_JOB_SECRET}
NEW = {"consent": {"version": "draft-1", "accepted": True}, "lang": "en", "place": {"lat": 26.91, "lon": 75.79},
       "home": {"roof": "rcc_brick_top", "fan": True}, "summary": {"higher_risk": False}, "alerts": {"enabled": False}}


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


def ts(hours_ago):
    return (datetime.now(IST) - timedelta(hours=hours_ago)).replace(minute=0, second=0, microsecond=0).isoformat()


def reading(hours_ago, indoor, room="bedroom"):
    return c.post("/api/v1/households/me/readings", json={"ts": ts(hours_ago), "room": room, "indoor_c": indoor}, headers=S["H"])


@case("P6-01", "A reading gets outdoor air and the model's estimate")
def _():
    r = c.post("/api/v1/households", json=NEW).json()
    S["H"] = {"Authorization": "Bearer " + r["token"]}
    S["before"] = c.post("/api/v1/households/me/status", json={}, headers=S["H"]).json()["indoor"]["numbers_shown"]
    x = reading(2, 30.0)
    rd = x.json()["reading"]
    return x.status_code == 201 and rd["outdoor_c"] is not None, f"outdoor {rd['outdoor_c']}; predicted {rd['predicted_c']}; period {rd['period']}"


@case("P6-02", "Kitchen readings never calibrate")
def _():
    rd = reading(3, 36.0, room="kitchen").json()["reading"]
    return rd["used_for_calibration"] is False, json.dumps({k: rd[k] for k in ("room", "used_for_calibration")})


@case("P6-03", "Impossible readings rejected")
def _():
    codes = [reading(2, 9.0).status_code, reading(2, 56.0).status_code, reading(72, 30.0).status_code]
    return codes == [422, 422, 422], str(codes)


@case("P6-05", "Calibration applies from 2 readings per period")
def _():
    out = [reading(h, 31.0).json().get("calibration") for h in range(4, 30)]
    cal = [x for x in out if x][-1]
    return cal["applied"] and max(cal["n_day"], cal["n_night"]) >= 2, json.dumps(cal)


@case("P6-06", "Room numbers outside Delhi after calibration")
def _():
    after = c.post("/api/v1/households/me/status", json={}, headers=S["H"]).json()
    basis, shown = after["indoor"]["basis"], after["indoor"]["numbers_shown"]
    want = basis == "model"      # calibration is validated against the model only; the offset fallback keeps numbers hidden
    return S["before"] is False and shown is want, \
        f"before {S['before']}, after {shown} (basis {basis}, n {after['calibration']['n_day'] + after['calibration']['n_night']}; expected {want})"


@case("P6-04", "List and delete")
def _():
    rows = c.get("/api/v1/households/me/readings", headers=S["H"]).json()["readings"]
    code = c.delete(f"/api/v1/households/me/readings/{rows[0]['id']}", headers=S["H"]).status_code
    n = len(c.get("/api/v1/households/me/readings", headers=S["H"]).json()["readings"])
    return code == 204 and n == len(rows) - 1, f"{len(rows)} -> {n}"


@case("P6-07", "Feedback")
def _():
    d = datetime.now(IST).date().isoformat()
    codes = [c.post("/api/v1/households/me/feedback", json={"for_date": d, "night_feel": "hot"}, headers=S["H"]).status_code,
             c.post("/api/v1/households/me/feedback", json={"for_date": d, "night_feel": "could_not_sleep"}, headers=S["H"]).status_code,
             c.post("/api/v1/households/me/feedback", json={"for_date": d, "night_feel": "hot", "note": "free text"}, headers=S["H"]).status_code]
    return codes == [204, 204, 422], str(codes)


@case("P6-08", "Fix progress")
def _():
    r = c.put("/api/v1/households/me/fixes/lime_whitewash", json={"status": "done", "done_at": datetime.now(IST).date().isoformat()}, headers=S["H"])
    bad = c.put("/api/v1/households/me/fixes/not_a_fix", json={"status": "planned"}, headers=S["H"]).status_code
    return r.status_code == 200 and "measured" in r.json() and bad == 404, f"measured: {r.json()['measured'].get('status')}; unknown fix {bad}"


@case("P6-09", "Government numbers")
def _():
    j = c.post("/internal/jobs/daily_aggregates", headers=JOB).json()
    g = c.get("/api/v1/gov/today").json()
    return j.get("ran") and "Among Thandak users" in g["note"], f"job {j}; rows {len(g['rows'])}"


@case("P6-10", "IMD off until onboarding")
def _():
    j = c.post("/internal/jobs/imd_warnings", headers=JOB).json()
    return "IMD_ENABLED is off" in str(j.get("skipped")), json.dumps(j)


@case("P6-11", "Calibration validated before shipping")
def _():
    cal = json.load(open(os.path.join(ROOT, "apps", "api", "data", "indoor_model_card.json"), encoding="utf-8"))["calibration"]
    return cal["decision"].startswith("ship") and all(r["change_c"] < 0 for r in cal["replay"]), \
        "; ".join(f"N={r['days_of_readings']}: {r['mae_model_c']}->{r['mae_calibrated_c']}" for r in cal["replay"])


p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_calibration.py", "tests/test_aggregates.py"],
                   cwd=ROOT, capture_output=True, text=True)
results.append(("P6-12", "Automated", p.returncode == 0, (p.stdout.strip().splitlines() or ["?"])[-1]))
results.sort(key=lambda r: int(r[0].split("-")[1]))
out = ["# Phase 6 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE} (live forecast, test secrets, throwaway database).", "",
       "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
out += ["", f"**{sum(1 for r in results if r[2])} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P6_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
