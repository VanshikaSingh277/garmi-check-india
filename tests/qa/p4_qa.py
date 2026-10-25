"""Phase 4 QA pack runner (docs/qa/P4_test_cases.md) against a server started with TEST secrets, a throwaway state
folder and HOUSEHOLDS_ENABLED=true (same environment for this script). Writes docs/qa/P4_results.md.
Usage (repo root):  python tests/qa/p4_qa.py <server-log-file>"""
import os
import sqlite3
import subprocess
import sys
import time

import httpx

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))
from app import config, secure  # noqa: E402

BASE = os.environ.get("QA_BASE", "http://localhost:8000")
LOG = sys.argv[1] if len(sys.argv) > 1 else None
c = httpx.Client(base_url=BASE, timeout=90)
results = []
tokens = []
NEW = {"consent": {"version": "draft-1", "accepted": True}, "lang": "en", "place": {"lat": 28.6139, "lon": 77.2090},
       "home": {"roof": "tin_top", "fan": True}, "summary": {"higher_risk": True, "share_counts": False},
       "alerts": {"enabled": True, "hour_ist": 19, "min_level": "high"}}


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


def auth(t):
    return {"Authorization": "Bearer " + t}


def db_dump():
    con = sqlite3.connect(config.DATABASE_URL[len("sqlite:///"):])
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


STATE = {}


@case("P4-01", "Save a home")
def _():
    r = c.post("/api/v1/households", json=NEW)
    STATE.update(r.json())
    tokens.append(STATE.get("token", ""))
    return r.status_code == 201 and len(STATE.get("token", "")) >= 40, f"{r.status_code}; token length {len(STATE.get('token', ''))}"


@case("P4-02", "No GPS, no token, no people stored")
def _():
    dump = db_dump()
    leaks = [x for x in ("28.6139", "77.209", STATE["token"]) if x in dump]
    return not leaks and "28.6" in dump, f"leaks: {len(leaks)}"


@case("P4-03", "Read and edit")
def _():
    me = c.get("/api/v1/households/me", headers=auth(STATE["token"])).json()
    p = c.patch("/api/v1/households/me", json={"place": {"lat": 26.91, "lon": 75.79}, "home": {"ac": True}}, headers=auth(STATE["token"])).json()
    return me["cell"] == {"lat": 28.6, "lon": 77.2} and p["district"] == "Jaipur" and p["home"]["ac"] and p["home"]["roof"] == "tin_top", \
        f"before {me['cell']}; after {p['cell']} {p['district']}; roof kept {p['home']['roof']}"


@case("P4-07", "Status with people from the phone")
def _():
    r = c.post("/api/v1/households/me/status", json={"people": [{"age_band": "older_65_74"}]}, headers=auth(STATE["token"])).json()
    return {"risk", "per_person", "today_actions", "calibration", "fixes"} <= set(r) and r["fan"]["group"] == "older", f"level {r['risk']['level']}; fan {r['fan']['group']}"


@case("P4-08", "Outlook")
def _():
    a = c.post("/api/v1/households/me/outlook", json={"days": 7}, headers=auth(STATE["token"]))
    b = c.post("/api/v1/households/me/outlook", json={"days": 8}, headers=auth(STATE["token"]))
    days = a.json()["days"]
    return 1 <= len(days) <= 7 and b.status_code == 422, f"{len(days)} days: {[d['level'] for d in days]}; days=8 -> {b.status_code}"


@case("P4-04", "Export")
def _():
    ph = "+919844400001"
    enc, kid = secure.encrypt_phone(ph)
    con = sqlite3.connect(config.DATABASE_URL[len("sqlite:///"):])
    con.execute("insert into push_target (id, household_id, kind, phone_enc, key_id, phone_hmac, verified_via, created_at, fail_count, active) "
                "values ('00000000-0000-4000-8000-0000000000aa', ?, 'sms', ?, ?, ?, 'otp', datetime('now'), 0, 1)",
                (STATE["household_id"], enc, kid, secure.phone_hmac(ph)))
    con.commit()
    con.close()
    r = c.get("/api/v1/households/me/export", headers=auth(STATE["token"]))
    acts = [e["action"] for e in r.json()["consent_events"]]
    return r.status_code == 200 and "9844400001" not in r.text and "…01" in r.text and "given" in acts, f"masked={'…01' in r.text}; events {acts}"


@case("P4-05", "Rotate token")
def _():
    new = c.post("/api/v1/households/me/token/rotate", json={}, headers=auth(STATE["token"])).json()["token"]
    tokens.append(new)
    old_code, new_code = c.get("/api/v1/households/me", headers=auth(STATE["token"])).status_code, c.get("/api/v1/households/me", headers=auth(new)).status_code
    STATE["token"] = new
    return (old_code, new_code) == (401, 200), f"old {old_code}, new {new_code}"


@case("P4-11", "Browser push only to real push services")
def _():
    keys = {"p256dh": "x" * 87, "auth": "y" * 22}
    bad = c.post("/api/v1/push", json={"kind": "webpush", "endpoint": "https://evil.example.com/x", "keys": keys}, headers=auth(STATE["token"])).status_code
    ok = c.post("/api/v1/push", json={"kind": "webpush", "endpoint": "https://fcm.googleapis.com/fcm/send/qa", "keys": keys}, headers=auth(STATE["token"])).status_code
    return (bad, ok) == (422, 201), f"evil {bad}, google {ok}"


@case("P4-06", "Delete in one step")
def _():
    hid = STATE["household_id"]
    code = c.delete("/api/v1/households/me", headers=auth(STATE["token"])).status_code
    con = sqlite3.connect(config.DATABASE_URL[len("sqlite:///"):])
    left = [con.execute(q, (hid,)).fetchone()[0] for q in ("select count(*) from household where id=?", "select count(*) from push_target where household_id=?")]
    events = sorted(r[0] for r in con.execute("select action from consent_event where household_id=?", (hid,)))
    con.close()
    return code == 204 and left == [0, 0] and "deleted" in events, f"{code}; left {left}; events {events}"


@case("P4-09", "Bad requests")
def _():
    codes = [c.post("/api/v1/households", json={**NEW, "consent": {"version": "old", "accepted": True}}).status_code,
             c.post("/api/v1/households", json={**NEW, "consent": {"version": "draft-1", "accepted": False}}).status_code,
             c.post("/api/v1/households", json={**NEW, "place": {"lat": 10.0, "lon": 70.0}}).status_code,
             c.post("/api/v1/households", json={**NEW, "gps": [28.6, 77.2]}).status_code,
             c.get("/api/v1/households/me").status_code]
    return codes == [409, 422, 422, 422, 401], str(codes)


@case("P4-12", "Web push key when not set up")
def _():
    r = c.get("/api/v1/vapid-public-key")
    return r.status_code == 503 and r.json()["error"] == "not_configured", f"{r.status_code} {r.text}"


@case("P4-13", "Tokens never in logs")
def _():
    time.sleep(0.5)
    text = open(LOG, encoding="utf-8", errors="replace").read() if LOG else ""
    return LOG is not None and not any(t and t in text for t in tokens) and "Bearer" not in text, f"tokens checked: {len(tokens)}"


@case("P4-10", "New-home limit (runs last)")
def _():
    codes = [c.post("/api/v1/households", json=NEW).status_code for _ in range(61)]
    first = codes.index(429) + 1 if 429 in codes else None
    return first is not None and first <= 61, f"first 429 at create {first} (earlier creates in this run count too)"


p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_households.py"], cwd=ROOT, capture_output=True, text=True)
results.append(("P4-14", "Push crypto and FCM", p.returncode == 0, (p.stdout.strip().splitlines() or ["?"])[-1]))
results.sort(key=lambda r: int(r[0].split("-")[1]))
out = ["# Phase 4 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE} with test secrets, a throwaway database and HOUSEHOLDS_ENABLED=true.", "",
       "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
out += ["", f"**{sum(1 for r in results if r[2])} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P4_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
