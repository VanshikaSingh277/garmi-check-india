"""Phase 7 QA pack runner (docs/qa/P7_test_cases.md). Needs two servers you run yourself with TEST secrets:
QA_BASE (default limits) and QA_LOAD_BASE (RATE_STATELESS_PER_MIN high), and this shell's environment set like QA_BASE's
server (same THANDAK_STATE_DIR and BACKUP_ENC_KEY) for the restore check. Writes docs/qa/P7_results.md.
Usage: python tests/qa/p7_qa.py"""
import glob
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
API = os.path.join(ROOT, "apps", "api")
sys.path.insert(0, API)
from app import config  # noqa: E402

BASE = os.environ.get("QA_BASE", "http://localhost:8001")
LOAD = os.environ.get("QA_LOAD_BASE", "http://localhost:8000")
PY = sys.executable
results = []


def sh(args, cwd=ROOT, timeout=900):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def case(cid, title):
    def wrap(fn):
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append((cid, title, ok, note))
        return fn
    return wrap


@case("P7-01", "Attack smoke")
def _():
    rc, out = sh([PY, "-X", "utf8", "scripts/attack_smoke.py", BASE])
    return rc == 0, re.search(r"\*\*(.+?)\*\*", out).group(1)


@case("P7-02", "Peak-evening load")
def _():
    rc, out = sh([PY, "-X", "utf8", "scripts/peak_load.py", LOAD, "--users", "50", "--seconds", "30", "--homes", "10"])
    total = next(line for line in out.splitlines() if line.startswith("| all |"))
    return rc == 0, f"{total.strip()} {re.search(r'[0-9.]+ requests/s', out).group(0)}"


def _pytest(expr):
    rc, out = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_p7_release.py", "-k", expr])
    return rc == 0, out.strip().splitlines()[-1]


@case("P7-03", "CGNAT")
def _():
    return _pytest("cgnat")


@case("P7-04", "Made-up tokens")
def _():
    return _pytest("made_up_tokens")


@case("P7-05", "No secrets in the repo")
def _():
    return _pytest("secret_shaped")


@case("P7-06", "Backup restore")
def _():
    rc, out = sh([PY, "-X", "utf8", "-m", "app.backup", "make"], cwd=API)
    newest = sorted(glob.glob(os.path.join(config.BACKUP_DIR, "thandak-*.db.enc")))[-1]
    encrypted = not open(newest, "rb").read(16).startswith(b"SQLite format 3")
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "restored.db")
        rc2, _ = sh([PY, "-X", "utf8", "-m", "app.backup", "restore", newest, target], cwd=API)
        new = sqlite3.connect(target)
        live = sqlite3.connect(config.DATABASE_URL.split("///", 1)[1])
        same = all(new.execute(f"select count(*) from {t}").fetchone() == live.execute(f"select count(*) from {t}").fetchone()
                   for t in ("household", "consent_event", "alembic_version"))
        integrity = new.execute("pragma integrity_check").fetchone()[0]
        n = new.execute("select count(*) from household").fetchone()[0]
        new.close()
        live.close()
    return rc == 0 and rc2 == 0 and encrypted and same and integrity == "ok", \
        f"encrypted {encrypted}; integrity {integrity}; counts match {same} ({n} homes)"


@case("P7-07", "Packages pinned with hashes")
def _():
    lock = open(os.path.join(API, "requirements.lock"), encoding="utf-8").read()
    pins = re.findall(r"^[A-Za-z0-9_.-]+==\S+ \\\n    --hash=sha256:[0-9a-f]{64}$", lock, re.M)
    names = re.findall(r"^[A-Za-z0-9_.-]+==", lock, re.M)
    rc, out = sh([os.path.join(os.path.dirname(PY), "pip-audit"), "--no-deps", "--disable-pip", "-r", "requirements.lock"], cwd=API)
    return len(pins) == len(names) > 20 and rc == 0, f"{len(pins)} packages hashed; {out.strip().splitlines()[-1]}"


@case("P7-08", "Container hardening")
def _():
    d = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    ig = open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8").read()
    checks = {
        "base images by digest": len(re.findall(r"^FROM \S+@sha256:[0-9a-f]{64}", d, re.M)) == 2,
        "require-hashes": "--require-hashes" in d,
        "non-root USER": re.search(r"^USER (?!root|0\b)\S+", d, re.M) is not None,
        "uvicorn flags": all(f in d for f in ("--no-access-log", "--no-server-header", "--no-proxy-headers")),
        ".env and state ignored": all(x in ig for x in ("**/.env", "apps/api/.env*", "apps/api/.cache", "**/*.db")),
    }
    return all(checks.values()), "; ".join(f"{k}: {'ok' if v else 'MISSING'}" for k, v in checks.items())


@case("P7-09", "Deploy and incident docs")
def _():
    dep = open(os.path.join(ROOT, "docs", "DEPLOY.md"), encoding="utf-8").read()
    inc = open(os.path.join(ROOT, "docs", "INCIDENT.md"), encoding="utf-8").read()
    return "read-only" in dep and "DRAFT" in inc and "TO VERIFY" in inc, f"DEPLOY {len(dep)} chars; INCIDENT {len(inc)} chars, DRAFT"


@case("P7-10", "Checks")
def _():
    notes, ok = [], True
    for name, args, cwd in [("ruff", [os.path.join(os.path.dirname(PY), "ruff"), "check", "."], API),
                            ("mypy", [os.path.join(os.path.dirname(PY), "mypy"), "app"], API),
                            ("bandit", [os.path.join(os.path.dirname(PY), "bandit"), "-q", "-c", "pyproject.toml", "-r", "app", "engine", "main.py"], API),
                            ("pip-audit", [os.path.join(os.path.dirname(PY), "pip-audit"), "-r", "requirements.txt"], API),
                            ("tests", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"], ROOT)]:
        rc, out = sh(args, cwd=cwd)
        ok = ok and rc == 0
        notes.append(f"{name}: {'ok' if rc == 0 else 'FAIL'}" + (f" ({out.strip().splitlines()[-1]})" if name == "tests" else ""))
    return ok, "; ".join(notes)


out = ["# Phase 7 test results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')}: attack against {BASE}, load against {LOAD} (test secrets, throwaway state).",
       "", "| ID | Title | Result | Notes |", "|---|---|---|---|"]
out += [f"| {cid} | {title} | {'PASS' if ok else 'FAIL'} | {note.replace('|', '/')} |" for cid, title, ok, note in results]
out += ["", f"**{sum(1 for r in results if r[2])} of {len(results)} passed.**", ""]
with open(os.path.join(ROOT, "docs", "qa", "P7_results.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out[4:]))
