"""Solution catalogue (data/solutions.csv). A solution is shown only if its effect key is usable in verified_numbers
(blueprint rule). Cooling fixes and health measures are listed separately (never mixed: degC vs people).

Selection is a transparent filter, not a model: role -> roof type -> roof access -> verified evidence. Every shown fix
carries the reasons it was chosen ("why"), every hidden one the reason it was hidden ("skipped"), and fixes are ordered
by cost tier (free -> low -> medium -> high)."""
import csv
import os
from functools import lru_cache

from . import verified as V

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "solutions.csv")
TIER_ORDER = {"free": 0, "low": 1, "medium": 2, "high": 3, "": 4}


@lru_cache(maxsize=1)
def catalogue():
    with open(PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick(role: str, roof: str = "any", roof_access: bool = True, lang: str = "en") -> dict:
    out = {"free": [], "cooling": [], "health": [], "avoid": [], "skipped": []}
    sx = "_hi" if lang == "hi" else "_en"
    for s in catalogue():
        if role not in s["roles"].split("|"):
            continue  # not meant for this audience at all - not worth listing as "skipped"
        roofs = s["applies_roof"].split("|")
        if s["applies_roof"] != "any" and roof != "any" and roof not in roofs:
            out["skipped"].append({"id": s["id"], "name": s["name" + sx], "reason": "roof_mismatch", "roofs": roofs})
            continue
        if "roof_access" in s["requires"] and not roof_access:
            out["skipped"].append({"id": s["id"], "name": s["name" + sx], "reason": "no_roof_access"})
            continue
        ek = s["effect_key"]
        if ek and not V.usable(ek):
            out["skipped"].append({"id": s["id"], "name": s["name" + sx], "reason": "evidence_not_verified"})
            continue
        why = []
        if s["tier"] == "free":
            why.append("free")
        if s["applies_roof"] != "any" and roof != "any":
            why.append("roof:" + roof)
        if "roof_access" in s["requires"]:
            why.append("roof_access")
        if s["section"] == "avoid":
            why.append("avoid_harm")
        if ek:
            why.append("evidence:" + V.table()[ek]["status"].split(" ")[0].split("(")[0].strip())
        out[s["section"]].append({
            "id": s["id"], "name": s["name" + sx], "what": s["what" + sx], "effect": s["effect_text" + sx],
            "cost": s["cost_text" + sx], "time": s["time" + sx], "who": s["who" + sx], "tier": s["tier"], "why": why,
            "evidence_status": V.table()[ek]["status"] if ek else "",
            "cost_status": V.table()[s["cost_key"]]["status"] if s["cost_key"] else "",
            "source": s["source_url"]})
    for k in ("free", "cooling", "health", "avoid"):
        out[k].sort(key=lambda x: TIER_ORDER.get(x["tier"], 4))
    return out
