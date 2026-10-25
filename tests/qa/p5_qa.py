"""Phase 5 QA pack runner (docs/qa/P5_test_cases.md) against a server started with TEST secrets and a throwaway
state folder (same environment here). Creates orgs with the CLI. Writes docs/qa/P5_results.md.
Usage (repo root):  python tests/qa/p5_qa.py <server-log-file>"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

import httpx

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
API = os.path.join(ROOT, "apps", "api")
sys.path.insert(0, API)
from app import config  # noqa: E402

BASE = os.environ.get("QA_BASE", "http://localhost:8000")
LOG = sys.argv[1] if len(sys.argv) > 1 else None
OUTBOX = os.path.join(config.STATE_DIR, "outbox.jsonl")
c = httpx.Client(base_url=BASE, timeout=90)
results, S, tokens = [], {}, []
PEOPLE = [{"age_band": "older_75_plus", "nickname": "Dadiqa", "conditions": ["kidney"], "medicine_classes": ["water_pill"], "lives_alone": True},
          {"age_band": "infant_0_1", "nickname": "Munniqa"}]
CONSENT = {"version": "draft-1", "by": "worker", "script_version": "draft-1"}


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


def cli(*args):
    p = subprocess.run([sys.executable, "-m", "app.admin", *args], cwd=API, capture_output=True, text=True, env=os.environ)
    return p.returncode, p.stdout.strip()


def last_code(suffix):
    rows = [json.loads(x) for x in open(OUTBOX, encoding="utf-8")] if os.path.exists(OUTBOX) else []
    return [r for r in rows if r["template"] == "otp" and r["to"] == "…" + suffix][-1]["text"][:6]


def login(phone):
    c.post("/api/v1/otp/send", json={"phone": phone, "purpose": "worker_login"})
    r = c.post("/api/v1/otp/verify", json={"phone": phone, "code": last_code(phone[-2:]), "purpose": "worker_login"}).json()
    tokens.append(r["token"])
    return r["token"]


def H(t):
    return {"Authorization": "Bearer " + t}


def db():
    return sqlite3.connect(config.DATABASE_URL[len("sqlite:///"):])


@case("P5-01", "Org and first admin only by CLI")
def _():
    a, out1 = cli("create-org", "--name", "QA NGO one", "--type", "ngo", "--state", "Delhi")
    b, out2 = cli("create-org", "--name", "QA NGO two", "--type", "ngo", "--state", "Delhi")
    S["org1"], S["org2"] = out1.split()[-1], out2.split()[-1]
    e, _ = cli("invite-admin", "--org", S["org1"], "--name", "QA Admin", "--phone", "+919660000001")
    f, _ = cli("invite-admin", "--org", S["org2"], "--name", "QA Admin Two", "--phone", "+919660000002")
    post_org = c.post("/api/v1/orgs", json={"name": "x", "type": "ngo"}).status_code
    return (a, b, e, f) == (0, 0, 0, 0) and post_org in (404, 405), f"CLI exit codes {(a, b, e, f)}; POST /api/v1/orgs -> {post_org}"


@case("P5-02", "Worker sign-in by OTP")
def _():
    S["admin"] = login("+919660000001")
    S["admin2"] = login("+919660000002")
    con = db()
    life = con.execute("select (julianday(expires_at) - julianday(created_at)) * 24 from worker_session order by created_at desc limit 1").fetchone()[0]
    con.close()
    return bool(S["admin"]) and 11.5 < life <= 12.01, f"admin session {life:.1f} h"


@case("P5-03", "No number probing")
def _():
    n0 = sum(1 for _ in open(OUTBOX, encoding="utf-8")) if os.path.exists(OUTBOX) else 0
    a = c.post("/api/v1/otp/send", json={"phone": "+919669999999", "purpose": "worker_login"}).json()
    n1 = sum(1 for _ in open(OUTBOX, encoding="utf-8"))
    v = c.post("/api/v1/otp/verify", json={"phone": "+919669999999", "code": "123456", "purpose": "worker_login"}).status_code
    return a == {"sent": True, "expires_in_s": 600} and n1 == n0 and v == 400, f"answer {a}; SMS sent {n1 - n0}; verify {v}"


@case("P5-04", "Admin invites workers")
def _():
    codes = [c.post(f"/api/v1/orgs/{S['org1']}/workers", json={"display_name": n, "phone": p, "role": "asha"}, headers=H(S["admin"])).status_code
             for n, p in (("QA Asha A", "+919660000011"), ("QA Asha B", "+919660000012"), ("QA Asha B again", "+919660000012"))]
    S["wa"], S["wb"] = login("+919660000011"), login("+919660000012")
    return codes == [201, 201, 409], str(codes)


@case("P5-05", "Worker adds a home with the consent script")
def _():
    r = c.post("/api/v1/workers/me/households", json={"consent": CONSENT, "lang": "hi", "place": {"lat": 28.6139, "lon": 77.2090},
                                                      "home": {"roof": "tin_top"}, "people": PEOPLE}, headers=H(S["wa"]))
    S["hid"] = r.json().get("household_id")
    con = db()
    ev = con.execute("select action, by from consent_event where household_id=?", (S["hid"],)).fetchall()
    con.close()
    return r.status_code == 201 and ev == [("given", "worker")], f"{r.status_code}; consent {ev}"


@case("P5-06", "People encrypted at rest")
def _():
    con = db()
    dump = "\n".join(con.iterdump())
    con.close()
    leaks = [x for x in ("Dadiqa", "Munniqa", "kidney", "water_pill") if x in dump]
    return not leaks, f"clear-text found: {leaks}"


@case("P5-07", "Worker isolation")
def _():
    codes = [c.patch(f"/api/v1/workers/me/households/{S['hid']}", json={"lang": "en"}, headers=H(S["wb"])).status_code,
             c.delete(f"/api/v1/workers/me/households/{S['hid']}", headers=H(S["wb"])).status_code]
    listed = S["hid"] in c.get("/api/v1/workers/me/households", headers=H(S["wb"])).text
    return codes == [404, 404] and not listed, f"{codes}; in B's list: {listed}"


@case("P5-08", "Org isolation")
def _():
    wid_b = c.get("/api/v1/workers/me", headers=H(S["wb"])).json()["worker_id"]
    S["wid_b"] = wid_b
    code = c.patch(f"/api/v1/orgs/{S['org2']}/households/{S['hid']}", json={"worker_id": wid_b}, headers=H(S["admin2"])).status_code
    return code == 404, str(code)


@case("P5-12", "Brief has no health details")
def _():
    t = c.get("/api/v1/workers/me/brief", params={"format": "text", "day": "today"}, headers=H(S["wa"])).json()["text"]
    bad = [w for w in ("kidney", "किडनी", "diuretic", "ड्यूरेटिक", "medicine", "दवा", "pill") if w in t]
    return not bad, f"{t[:90]!r}; health words: {bad}"


@case("P5-09", "Access log")
def _():
    c.get("/api/v1/workers/me/households", headers=H(S["wa"]))
    c.patch(f"/api/v1/workers/me/households/{S['hid']}", json={"home": {"fan": True}}, headers=H(S["wa"]))
    con = db()
    wid = con.execute("select worker_id from household where id=?", (S["hid"],)).fetchone()[0]
    acts = sorted({r[0] for r in con.execute("select action from access_log where household_id=? and worker_id=?", (S["hid"], wid))})
    con.close()
    return acts == ["brief", "create", "edit", "view"], str(acts)


@case("P5-10", "Reassignment")
def _():
    a = c.patch(f"/api/v1/orgs/{S['org1']}/households/{S['hid']}", json={"worker_id": S["wid_b"]}, headers=H(S["admin"])).status_code
    old = c.patch(f"/api/v1/workers/me/households/{S['hid']}", json={"lang": "en"}, headers=H(S["wa"])).status_code
    new = c.patch(f"/api/v1/workers/me/households/{S['hid']}", json={"lang": "en"}, headers=H(S["wb"])).status_code
    return (a, old, new) == (200, 404, 200), str((a, old, new))


@case("P5-11", "Deactivation revokes sessions")
def _():
    wid_a = c.get("/api/v1/workers/me", headers=H(S["wa"])).json()["worker_id"]
    a = c.patch(f"/api/v1/orgs/{S['org1']}/workers/{wid_a}", json={"active": False}, headers=H(S["admin"])).status_code
    b = c.get("/api/v1/workers/me", headers=H(S["wa"])).status_code
    return (a, b) == (200, 401), str((a, b))


@case("P5-13", "Delete on the family's request")
def _():
    code = c.delete(f"/api/v1/workers/me/households/{S['hid']}", headers=H(S["wb"])).status_code
    con = db()
    left = con.execute("select count(*) from person where household_id=?", (S["hid"],)).fetchone()[0]
    ev = sorted(r[0] for r in con.execute("select action from consent_event where household_id=?", (S["hid"],)))
    con.close()
    return code == 204 and left == 0 and ev == ["deleted", "given"], f"{code}; people left {left}; events {ev}"


@case("P5-14", "Logs hold no names or numbers")
def _():
    time.sleep(0.5)
    text = open(LOG, encoding="utf-8", errors="replace").read() if LOG else ""
    leaks = [x for x in ("Dadiqa", "Munniqa", "9660000001", "9660000011", *tokens) if x and x in text]
    return LOG is not None and not leaks and not re.search(r"\b[6-9]\d{9}\b", text), f"leaks: {len(leaks)}"


p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_worker.py"], cwd=ROOT, capture_output=True, text=True)
results.append(("P5-15", "Automated isolation tests", p.returncode == 0, (p.stdout.strip().splitlines() or ["?"])[-1]))
results.sort(key=lambda r: int(r[0].split("-")[1]))
out = ["# Phase 5 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE} with test secrets and a throwaway database.", "",
       "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
out += ["", f"**{sum(1 for r in results if r[2])} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P5_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
