"""data/MANIFEST.json: SHA-256 of every safety data file, checked at startup (spec §8.9). In prod a mismatch stops the
server; in dev it is logged.

Rebuild after changing data on purpose:  python -m app.manifest build   (from apps/api)"""
import hashlib
import json
import logging
import os
import sys

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PATH = os.path.join(DATA, "MANIFEST.json")
log = logging.getLogger("thandak")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _files(data_dir: str) -> list[str]:
    return sorted(f for f in os.listdir(data_dir) if f != "MANIFEST.json" and os.path.isfile(os.path.join(data_dir, f)))


def build(data_dir: str = DATA) -> dict:
    m = {"about": "SHA-256 of each data file; verified at startup (BACKEND_SPEC §8.9). Rebuild: python -m app.manifest build",
         "files": {f: _sha256(os.path.join(data_dir, f)) for f in _files(data_dir)}}
    with open(os.path.join(data_dir, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1)
        fh.write("\n")
    return m


def problems(data_dir: str = DATA) -> list[str]:
    """Files that are missing, changed or not listed. Empty when everything matches."""
    path = os.path.join(data_dir, "MANIFEST.json")
    if not os.path.exists(path):
        return ["MANIFEST.json missing"]
    want = json.load(open(path, encoding="utf-8"))["files"]
    have = set(_files(data_dir))
    out = [f"{f}: missing" for f in want if f not in have]
    out += [f"{f}: changed" for f in want if f in have and _sha256(os.path.join(data_dir, f)) != want[f]]
    out += [f"{f}: not in manifest" for f in sorted(have - set(want))]
    return out


def verify(prod: bool, data_dir: str = DATA) -> list[str]:
    bad = problems(data_dir)
    if bad and prod:
        raise RuntimeError("data/ does not match MANIFEST.json: " + "; ".join(bad))
    for b in bad:
        log.warning("data manifest: %s", b)
    return bad


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        print(len(build()["files"]), "files")
    else:
        bad = problems()
        print("\n".join(bad) or "ok")
        sys.exit(1 if bad else 0)
