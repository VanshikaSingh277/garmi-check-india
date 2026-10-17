"""Single source of truth: every threshold/effect the app uses is read from docs/verified_numbers.csv.
Nothing numeric about health or fix effects is hard-coded elsewhere (blueprint rule)."""
import csv
import json
import os
from functools import lru_cache

DEFAULT = os.path.join(os.path.dirname(__file__), "..", "data", "verified_numbers.csv")


@lru_cache(maxsize=1)
def table(path: str = DEFAULT) -> dict:
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["value_parsed"] = json.loads(row["value"]) if row["value"] not in ("", "null") else None
            except json.JSONDecodeError:
                row["value_parsed"] = None
            out[row["key"]] = row
    return out


def value(key: str):
    return table()[key]["value_parsed"]


def source(key: str) -> dict:
    r = table()[key]
    return {"key": key, "title": r["source_title"], "url": r["doi_or_url"], "status": r["status"]}


def usable(key: str) -> bool:
    """A feature may only use a row that is not UNVERIFIED/DISPUTED-blocking."""
    st = table()[key]["status"].upper()
    return not st.startswith("UNVERIFIED") and "TO VERIFY" not in st
