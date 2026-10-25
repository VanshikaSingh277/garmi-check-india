"""Phase 3 QA pack runner (docs/qa/P3_test_cases.md) against a running server; writes docs/qa/P3_results.md.
Usage (repo root):  python tests/qa/p3_qa.py <server-log-file>"""
import json
import os
import re
import subprocess
import sys
import time

import httpx

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BASE = os.environ.get("QA_BASE", "http://localhost:8000")
LOG = sys.argv[1] if len(sys.argv) > 1 else None
c = httpx.Client(base_url=BASE, timeout=90)
results = []
BODY = {"lat": 28.61, "lon": 77.21, "roof": "tin_top", "devices": {"fan": True}, "lang": "en"}


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


def st(**kw):
    return c.post("/api/status/individual", json={**BODY, **kw})


@case("P3-01", "Old form still works")
def _():
    r = st(vulnerable=["elderly", "child"]).json()
    return [p["reasons"] for p in r["per_person"]] == [["older"], ["child"]], str([p["reasons"] for p in r["per_person"]])


@case("P3-02", "People list accepted")
def _():
    r = st(people=[{"age_band": "older_65_74", "lives_alone": True}, {"age_band": "infant_0_1"}]).json()
    return len(r["per_person"]) == 2 and r["fan"]["group"] == "older", f"{len(r['per_person'])} people; fan group {r['fan']['group']}"


@case("P3-03", "Level unchanged by people")
def _():
    a, b = st().json()["risk"], st(people=[{"age_band": "older_75_plus", "conditions": ["heart"]}]).json()["risk"]
    return a["level"] == b["level"] and [x["code"] for x in a["reasons"]] == [x["code"] for x in b["reasons"]], f"{a['level']} / {b['level']}"


@case("P3-04", "No per-person level")
def _():
    pp = st(people=[{"age_band": "older_65_74"}]).json()["per_person"][0]
    return "level" not in pp and isinstance(pp["higher_risk_today"], bool), json.dumps({k: pp[k] for k in ("higher_risk_today", "reasons")})


@case("P3-05", "Nickname echoed, never logged")
def _():
    r = st(people=[{"age_band": "older_65_74", "nickname": "Dadiqa"}]).json()
    time.sleep(0.5)
    in_log = LOG is not None and "Dadiqa" in open(LOG, encoding="utf-8", errors="replace").read()
    return r["per_person"][0]["label"] == "Dadiqa" and LOG is not None and not in_log, f"label={r['per_person'][0]['label']}; in server log={in_log}"


@case("P3-06", "Unsafe nickname rejected")
def _():
    r = st(people=[{"age_band": "older_65_74", "nickname": "<script>"}])
    return r.status_code == 422 and "<script>" not in r.text, f"{r.status_code} {r.text[:100]}"


@case("P3-07", "Unknown person fields rejected")
def _():
    bad = [{"age_band": "adult_15_64", "conditions": ["cancer"]}, {"age_band": "adult_15_64", "medicine_classes": ["aspirin"]},
           {"age_band": "adult_15_64", "name": "Ravi"}, {"age_band": "adult_15_64", "work_start": "25:00"}]
    codes = [st(people=[p]).status_code for p in bad]
    return codes == [422] * 4, str(codes)


@case("P3-08", "Hindi actions")
def _():
    r = st(lang="hi", people=[{"age_band": "infant_0_1"}, {"age_band": "older_65_74"}]).json()
    acts = r["today_actions"]
    hindi = all(re.search(r"[ऀ-ॿ]", a["text"]) for a in acts)
    left = any(re.search(r"\{[a-zA-Z]", a["text"]) for a in acts)
    return hindi and not left, f"{len(acts)} actions (level {r['risk']['level']}); all Hindi={hindi}; placeholders left={left}"


@case("P3-09", "Power cut and AC inputs")
def _():
    ok = st(devices={"fan": True, "ac": True}, power_cut_hours=[["14:00", "16:00"]]).json()
    ac = [a for a in ok["today_actions"] if a["code"] == "use_ac_hours"]
    inside = any(a < "16:00" and b > "14:00" for x in ac for a, b in x["hours"])
    bad = st(power_cut_hours=[["14:00", "26:00"]]).status_code
    return not inside and bad == 422, f"AC hours inside the cut={inside}; bad time -> {bad}"


for cid, title, test in (("P3-10", "Golden cases G1-G12", "tests/test_golden.py"), ("P3-11", "Per-person rules", "tests/test_people_rules.py")):
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test], cwd=ROOT, capture_output=True, text=True)
    results.append((cid, title, p.returncode == 0, (p.stdout.strip().splitlines() or ["?"])[-1]))

results.sort(key=lambda r: int(r[0].split("-")[1]))
out = ["# Phase 3 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} against {BASE} (live forecast).", "",
       "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
out += ["", f"**{sum(1 for r in results if r[2])} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P3_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
