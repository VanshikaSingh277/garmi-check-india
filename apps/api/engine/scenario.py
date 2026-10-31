"""Ward cooling scenarios (Delhi): convert part of a ward's built-up or bare land to tree cover and estimate the change in its
mean surface temperature, by day and by night. Coefficients, validation and caveats: data/ward_scenario.json
(built by ml/model_a/train_ward_scenario.py). Government planning aid only: it never touches anyone's heat level."""
import json
import os
from functools import lru_cache

from . import verified as V

HERE = os.path.dirname(__file__)
PATH = os.path.join(HERE, "..", "data", "ward_scenario.json")
SOURCES = ("built", "bare")


@lru_cache(maxsize=1)
def _card() -> dict:
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def _delta(m: dict, source: str, share: float, which: str) -> float:
    per = m[which]
    # built-up is the model's reference cover, so its coefficient is zero by construction
    return share * (per["tree"] - (0.0 if source == "built" else per[source]))


def simulate(wards: list, tree_pp: float, source: str) -> dict:
    """wards: rows from gov_rank.json (ward_no, ward_name, district, pop_total, pop_65plus). tree_pp: percentage points of the
    ward's area to convert. A ward can't convert more than it has of the source cover."""
    card = _card()
    out, pop, pop65, wday, wnight, km2 = [], 0.0, 0.0, 0.0, 0.0, 0.0
    for w in wards:
        cover = card["wards"].get(w["ward_no"])
        if not cover:
            continue
        share = min(tree_pp / 100.0, cover[source])
        row = {"ward_no": w["ward_no"], "ward_name": w["ward_name"], "district": w["district"],
               "tree_now": cover["tree"], "tree_after": round(cover["tree"] + share, 4), "converted": round(share, 4),
               "pop_total": round(w.get("pop_total") or 0), "pop_65plus": round(w.get("pop_65plus") or 0)}
        for key, m in card["model"].items():
            row[f"{key}_c"] = round(_delta(m, source, share, "per_share_c"), 2)
            ends = sorted([_delta(m, source, share, "per_share_p10_c"), _delta(m, source, share, "per_share_p90_c")])
            row[f"{key}_band_c"] = [round(ends[0], 2), round(ends[1], 2)]
        out.append(row)
        p = row["pop_total"]
        pop += p
        pop65 += row["pop_65plus"]
        km2 += share * (w.get("area_km2") or 0.0)
        wday += p * row["day_c"]
        wnight += p * row["night_c"]
    summary = {"wards": len(out), "pop_total": round(pop), "pop_65plus": round(pop65),
               "day_c_pop_weighted": round(wday / pop, 2) if pop else None, "night_c_pop_weighted": round(wnight / pop, 2) if pop else None,
               "area_converted_km2": round(km2, 2)}
    model = {k: {"cv_mae_c": m["cv_mae_c"], "baseline_mae_c": m["baseline_mae_c"]} for k, m in card["model"].items()}
    return {"tree_pp": tree_pp, "from": source, "summary": summary, "wards": out, "model": model,
            "method": card["method"], "validation": card["validation"], "uncertainty": card["uncertainty"],
            "data": card["data"], "trained": card["trained"], "caveats": card["caveats"]}


OBJECTIVES = ("people", "elderly", "vulnerable")


TREE_COST = "cost.tree_cover_per_km2"
ROOF_KEYS = ("cost.coolroof_per_m2", "coolroof.roof_area_per_home_m2", "household.persons_per_home")


def _shown(key: str):
    return V.value(key) if V.shown_ok(key) else None


def optimise(wards: list, area_km2: float | None, source: str, objective: str, max_pp: float,
             budget_inr: float | None = None) -> dict:
    """Best use of a planting budget: which wards should get area_km2 of new tree cover (on built-up or bare land) to give
    the most cooling where people live. The model is linear, so each km2 planted in a ward is worth a fixed amount
    (cooling per share x people / ward area); filling the best wards first, each up to its cap, is then optimal
    (a fractional knapsack). Caps: no ward converts more than max_pp points of its area, or more source land than it has.
    objective: people (all residents), elderly (65+), vulnerable (residents weighted by the ward's HVI).
    budget_inr instead of area_km2: rupees become km2 only through a verified cost row; without one nothing is placed."""
    if budget_inr is not None:
        per = _shown(TREE_COST)
        if not per:
            res = simulate([], 0, source)
            res.update({"objective": objective, "budget_inr": budget_inr, "area_km2": None, "max_pp": max_pp,
                        "area_used_km2": 0, "missing": [TREE_COST], "cost": None})
            return res
        area_km2 = budget_inr / per["inr_per_km2"]
    area_km2 = area_km2 or 0.0
    card = _card()
    day = card["model"]["day"]

    def weight(w):
        if objective == "elderly":
            return w.get("pop_65plus") or 0.0
        if objective == "vulnerable":
            return (w.get("pop_total") or 0.0) * (w.get("hvi") or 0.0)
        return w.get("pop_total") or 0.0

    cand = []
    for w in wards:
        cover, area = card["wards"].get(w["ward_no"]), w.get("area_km2") or 0.0
        if not cover or area <= 0:
            continue
        cap_share = min(max_pp / 100.0, cover[source])
        # cooling-weighted people per km2 planted (day): -delta per share / area x weight; larger is better
        value = -_delta(day, source, 1.0, "per_share_c") / area * weight(w)
        if cap_share > 0 and value > 0:
            cand.append((value, w, cap_share * area))
    cand.sort(key=lambda x: x[0], reverse=True)

    left, picked = area_km2, []
    for _value, w, cap_km2 in cand:
        if left <= 1e-9:
            break
        take = min(cap_km2, left)
        left -= take
        picked.append((w, take / w["area_km2"] * 100.0))
    # each picked ward gets its own share; reuse simulate() so the numbers and bands match the scenario tool exactly
    rows = []
    for w, pp in picked:
        rows += simulate([w], pp, source)["wards"]
    res = simulate([], 0, source)
    pop = sum(r["pop_total"] for r in rows)
    res.update({"objective": objective, "budget_inr": budget_inr, "area_km2": round(area_km2, 3), "max_pp": max_pp,
                "area_used_km2": round(area_km2 - left, 2), "wards": rows, "missing": []})
    res["summary"] = {"wards": len(rows), "pop_total": pop, "pop_65plus": sum(r["pop_65plus"] for r in rows),
                      "day_c_pop_weighted": round(sum(r["pop_total"] * r["day_c"] for r in rows) / pop, 2) if pop else None,
                      "night_c_pop_weighted": round(sum(r["pop_total"] * r["night_c"] for r in rows) / pop, 2) if pop else None,
                      "area_converted_km2": round(area_km2 - left, 2),
                      "cooling_person_c": round(sum(r["pop_total"] * r["day_c"] for r in rows))}
    # rupees only from a verified cost row; until the team supplies one, the planner works in km2 alone
    per = _shown(TREE_COST)
    res["cost"] = ({"inr": round(per["inr_per_km2"] * (area_km2 - left)), "inr_per_km2": per["inr_per_km2"],
                    "source": V.source(TREE_COST)} if per else None)
    return res


def plan_coolroofs(wards: list, budget_inr: float, objective: str) -> dict:
    """Best use of a cool-roof budget: which wards' sheet-roof homes (metal or asbestos) to treat first. The ward LST model
    can't speak for roofs, so the effect is the verified indoor-air drop for rooms under a treated roof, the same for every
    home, and it is never added to the tree figures. Every home costs the same and gains the same, so the order is the
    whole decision: elderly ranks wards by their 65+ share, people and vulnerable by HVI (with equal people per home, the
    head count is the same whichever wards come first). Sheet-roof homes per ward = residents x the district's Census 2011
    sheet-roof share / people per home; no ward gets more roofs than that."""
    effect = V.value("coolroof.indoor_drop")
    res: dict = {"objective": objective, "budget_inr": budget_inr,
                 "effect": {"indoor_drop_c": [effect["india_low"], effect["india_high"]], "source": V.source("coolroof.indoor_drop")},
                 "caveats": ["census_district_share", "under_treated_roof_only", "not_added_to_trees"],
                 "missing": [k for k in ROOF_KEYS if not V.shown_ok(k)], "wards": [], "summary": None, "cost": None}
    if res["missing"]:
        return res
    per_m2, m2, persons = (V.value(k) for k in ROOF_KEYS)
    per_home = per_m2["inr_per_m2"] * m2["m2"]
    size = persons["persons"]

    def rank(w):
        pop = w.get("pop_total") or 0.0
        return ((w.get("pop_65plus") or 0.0) / pop if objective == "elderly" and pop else 0.0, w.get("hvi") or 0.0)

    left, rows = budget_inr, []
    for w in sorted(wards, key=rank, reverse=True):
        pop = w.get("pop_total") or 0.0
        eligible = int(pop * (w.get("c2011_share_metal_sheet") or 0.0) / size)
        homes = min(eligible, int(left // per_home))
        if homes <= 0:
            if left < per_home:
                break
            continue
        left -= homes * per_home
        people = homes * size
        rows.append({"ward_no": w["ward_no"], "ward_name": w["ward_name"], "district": w["district"], "homes": homes,
                     "eligible_homes": eligible, "people": round(people),
                     "pop_65plus": round(people * (w.get("pop_65plus") or 0.0) / pop), "inr": round(homes * per_home)})
    res["wards"] = rows
    res["summary"] = {"wards": len(rows), "homes": sum(r["homes"] for r in rows), "people": sum(r["people"] for r in rows),
                      "pop_65plus": sum(r["pop_65plus"] for r in rows)}
    res["cost"] = {"inr": round(budget_inr - left), "inr_per_home": round(per_home), "inr_per_m2": per_m2["inr_per_m2"],
                   "roof_m2": m2["m2"], "persons_per_home": size, "source": V.source(ROOF_KEYS[0])}
    return res
