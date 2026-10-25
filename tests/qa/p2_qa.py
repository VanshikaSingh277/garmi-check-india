"""Phase 2 QA pack runner (docs/qa/P2_test_cases.md) against a running server started with TEST secrets and a
throwaway state folder (same environment for this script). Writes docs/qa/P2_results.md.

Usage (repo root):  python tests/qa/p2_qa.py <server-log-file>"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

import httpx

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
API = os.path.join(ROOT, "apps", "api")
sys.path.insert(0, API)
from app import config, secure  # noqa: E402

BASE = os.environ.get("QA_BASE", "http://localhost:8000")
LOG = sys.argv[1] if len(sys.argv) > 1 else None
OUTBOX = os.path.join(config.STATE_DIR, "outbox.jsonl")
c = httpx.Client(base_url=BASE, timeout=60)
results = []
JOB = {"x-job-secret": config.INTERNAL_JOB_SECRET}


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


def wa(text, phone, msg_id=None, ts=None, secret=None):
    body = json.dumps({"id": msg_id or f"qa-{time.time_ns()}", "from": phone, "text": text})
    ts = int(time.time()) if ts is None else ts
    sig = "sha256=" + secure.sign(f"{ts}.{body}", secret or config.WHATSAPP_WEBHOOK_SECRET)
    return c.post("/api/v1/webhooks/whatsapp", content=body, headers={"content-type": "application/json", "x-thandak-timestamp": str(ts),
                                                                      "x-thandak-signature": sig})


def outbox():
    if not os.path.exists(OUTBOX):
        return []
    return [json.loads(x) for x in open(OUTBOX, encoding="utf-8")]


def dbq(sql, *args):
    con = sqlite3.connect(config.DATABASE_URL[len("sqlite:///"):])
    try:
        rows = con.execute(sql, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


P1, P2N, P3 = "+919800000101", "+919800000102", "+919800000103"


@case("P2-01", "WhatsApp sign-up")
def _():
    replies = [wa(t, P1).json().get("reply") for t in ("HI", "302001", "YES", "1", "1")]
    want = ["ask_pin", "consent", "ask_lang", "ask_level", "signed_up"]
    rows = dbq("select h.cell_lat, h.cell_lon, h.district from household h join push_target t on t.household_id=h.id where t.phone_hmac=?", secure.phone_hmac(P1))
    return replies == want and len(rows) == 1 and rows[0][:2] == (26.9, 75.8), f"replies={replies}; home={rows}"


@case("P2-02", "Hindi sign-up")
def _():
    replies = [wa(t, P2N).json().get("reply") for t in ("HI", "302001", "YES", "2", "2")]
    last = [m for m in outbox() if m["to"] == "…" + P2N[-2:]][-1]["text"]
    return replies[-1] == "signed_up" and any("ऀ" <= ch <= "ॿ" for ch in last), f"replies={replies}; last reply: {last[:60]}"


@case("P2-03", "HELP and ALERT")
def _():
    a, b = wa("HELP", P1).json().get("reply"), wa("ALERT", P1).json().get("reply")
    help_text = [m for m in outbox() if m["template"] == "help"][-1]["text"]
    return a == "help" and b == "alert_now" and "112" in help_text, f"{a}, {b}; help mentions 112: {'112' in help_text}"


@case("P2-05", "Unsigned, old or forged webhook")
def _():
    codes = [c.post("/api/v1/webhooks/whatsapp", json={"id": "x", "from": P3, "text": "HI"}).status_code,
             wa("HI", P3, ts=int(time.time()) - 600).status_code, wa("HI", P3, secret="wrong").status_code]
    return codes == [401, 401, 401], str(codes)


@case("P2-06", "Repeated message id")
def _():
    n0 = len(outbox())
    a, b = wa("HI", P3, msg_id="qa-dup-1").json(), wa("HI", P3, msg_id="qa-dup-1").json()
    return b.get("duplicate") is True and len(outbox()) == n0 + 1, f"first={a}; second={b}"


@case("P2-07", "OTP send and limits")
def _():
    phone = "+919800000104"
    codes = [c.post("/api/v1/otp/send", json={"phone": phone, "purpose": "household_sms"}) for _ in range(4)]
    sent = [m for m in outbox() if m["template"] == "otp" and m["to"] == "…04"]
    leaked = any(m["text"][:6] in r.text for m in sent for r in codes)
    return [r.status_code for r in codes] == [200, 200, 200, 429] and "retry-after" in codes[3].headers and not leaked, \
        f"{[r.status_code for r in codes]}; code in a reply: {leaked}"


@case("P2-08", "OTP attempts")
def _():
    phone = "+919800000105"
    c.post("/api/v1/otp/send", json={"phone": phone, "purpose": "household_sms"})
    code = [m for m in outbox() if m["template"] == "otp" and m["to"] == "…05"][-1]["text"][:6]
    wrong = "000000" if code != "000000" else "111111"
    codes = [c.post("/api/v1/otp/verify", json={"phone": phone, "code": wrong, "purpose": "household_sms"}).status_code for _ in range(5)]
    last = c.post("/api/v1/otp/verify", json={"phone": phone, "code": code, "purpose": "household_sms"}).status_code
    return codes == [400] * 5 and last == 400, f"wrong: {codes}; right code after 5 wrong: {last}"


@case("P2-09", "Only Indian mobiles")
def _():
    r = c.post("/api/v1/otp/send", json={"phone": "+14155550100", "purpose": "household_sms"})
    return r.status_code == 422 and r.json()["error"] == "invalid_phone", f"{r.status_code} {r.text}"


@case("P2-10", "SMS target needs OTP proof")
def _():
    token = secure.new_token()
    dbq("insert into household (id, token_hash, lang, cell_lat, cell_lon, alerts_enabled, alert_hour_ist, alert_min_level, managed_by, "
        "higher_risk, share_counts, calib_n_day, calib_n_night, in_delhi, created_at, updated_at, last_seen_at) "
        "values (?, ?, 'en', 28.6, 77.2, 1, 19, 'high', 'self', 0, 0, 0, 0, 0, datetime('now'), datetime('now'), datetime('now'))",
        "00000000-0000-4000-8000-000000000001", secure.token_hash(token))
    auth = {"Authorization": "Bearer " + token}
    phone = "+919800000106"
    forged = c.post("/api/v1/push", json={"kind": "sms", "phone": phone, "proof": "x.y"}, headers=auth).status_code
    c.post("/api/v1/otp/send", json={"phone": phone, "purpose": "household_sms"})
    code = [m for m in outbox() if m["template"] == "otp" and m["to"] == "…06"][-1]["text"][:6]
    proof = c.post("/api/v1/otp/verify", json={"phone": phone, "code": code, "purpose": "household_sms"}).json()["proof"]
    real = c.post("/api/v1/push", json={"kind": "sms", "phone": phone, "proof": proof}, headers=auth).status_code
    return forged == 403 and real == 201, f"forged proof {forged}; real proof {real}"


@case("P2-11", "Internal routes need the secret")
def _():
    codes = [c.get("/internal/metrics").status_code, c.get("/internal/metrics", headers={"x-job-secret": "wrong"}).status_code,
             c.get("/internal/metrics", headers=JOB).status_code]
    return codes == [403, 403, 200], str(codes)


@case("P2-12", "Kill switch")
def _():
    r = c.post("/internal/jobs/send_queue", headers=JOB).json()
    return r.get("ran") and r.get("reason") == "ALERTS_ENABLED_GLOBAL is off" and r.get("sent") == 0, json.dumps(r)


@case("P2-13", "Jobs run once at a time")
def _():
    out = []
    ts = [threading.Thread(target=lambda: out.append(c.post("/internal/jobs/retention_purge", headers=JOB).json())) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    ran = [o.get("ran") for o in out]
    return sorted(ran) in ([False, True], [True, True]), f"ran={ran} (True,True means they ran one after the other)"


@case("P2-14", "Backup and restore")
def _():
    r = c.post("/internal/jobs/backup", headers=JOB).json()
    path = os.path.join(config.BACKUP_DIR, r["file"])
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "restored.db")
        p = subprocess.run([sys.executable, "-m", "app.backup", "restore", path, target], cwd=API, capture_output=True, text=True, env=os.environ)
        con = sqlite3.connect(target)
        n = con.execute("select count(*) from household").fetchone()[0]
        con.close()
    return p.returncode == 0 and n >= 1, f"backup {r['file']}; restored households: {n}"


@case("P2-15", "Outbox and logs hold no phone numbers")
def _():
    texts = open(OUTBOX, encoding="utf-8").read() + (open(LOG, encoding="utf-8", errors="replace").read() if LOG else "")
    leaks = [p for p in (P1, P2N, P3, "+919800000104", "+919800000105", "+919800000106") if p in texts or p[3:] in texts]
    return not leaks and LOG is not None, f"numbers found: {len(leaks)}; server log checked: {LOG is not None}"


@case("P2-04", "STOP deletes the home")
def _():
    ph = secure.phone_hmac(P1)
    hid = dbq("select household_id from push_target where phone_hmac=?", ph)[0][0]
    reply = wa("STOP", P1).json().get("reply")
    left = dbq("select count(*) from household where id=?", hid)[0][0]
    events = sorted(r[0] for r in dbq("select action from consent_event where household_id=?", hid))
    return reply == "stop_deleted" and left == 0 and events == ["deleted", "given", "withdrawn"], f"reply={reply}; household left={left}; events={events}"


@case("P2-16", "Health shows the database")
def _():
    h = c.get("/api/health").json()
    return h["db_ok"] is True, f"db_ok={h['db_ok']}"


@case("P2-17", "Migrations up and down")
def _():
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "DATABASE_URL": "sqlite:///" + os.path.join(d, "m.db").replace("\\", "/")}
        alembic = os.path.join(os.path.dirname(sys.executable), "alembic")
        steps = [subprocess.run([alembic, *a], cwd=API, env=env, capture_output=True, text=True).returncode
                 for a in (["upgrade", "head"], ["downgrade", "-1"], ["upgrade", "head"])]
    return steps == [0, 0, 0], f"exit codes {steps}"


for cid, title, test in (("P2-18", "No health words in messages", "tests/test_notify.py::test_no_health_words_in_any_template_or_alert_text"),
                         ("P2-19", "Alert rules", "tests/test_notify.py")):
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test], cwd=ROOT, capture_output=True, text=True)
    results.append((cid, title, p.returncode == 0, (p.stdout.strip().splitlines() or ["?"])[-1]))

results.sort(key=lambda r: int(r[0].split("-")[1]))
out = ["# Phase 2 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE} with test secrets and a throwaway database.", "",
       "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
out += ["", f"**{sum(1 for r in results if r[2])} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P2_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
