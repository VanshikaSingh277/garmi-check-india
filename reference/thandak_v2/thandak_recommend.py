"""
Thandak solution engine v2 - reference implementation (Python 3.11+, standard library only).

What changed from v1
--------------------
* Family fixes are triggered by the household's answers and today's heat level.
  Satellite area causes only boost ranking and add a "because" line for families,
  so a place with no satellite profile still gets full advice.
* New "today" tier: free actions that change with the forecast (window timing,
  care for vulnerable people, fan limits, cooler advice, outdoor work).
* Evaporative advice uses the forecast humidity for the next afternoon window
  (see afternoon_rh), not the reading at the hour the app was opened.
* "vulnerable" changes content (care actions, stricter fan profile), not just a score.
* Fixes blocked by budget, humidity or climate come back in "excluded" with a reason.
* Fixes with a measured number rank above unmeasured ones; global-review numbers
  are not shown as a degC range.
* Bad optional inputs are normalised or ignored with a warning; they never blank
  the result. Missing translations are reported in "needs_translation".
* estimate_fix_effect() turns a home's before/after thermometer readings into an
  effect estimate that corrects for hotter or cooler weeks.

Usage
-----
    python thandak_recommend.py      # demo
    python -m unittest -v            # tests (test_thandak_recommend.py)

    from thandak_recommend import recommend, afternoon_rh
    weather = {"heat_level": "high",                       # from Thandak's heat-level rules
               "afternoon_rh_pct": afternoon_rh(times, rh, now)}
    out = recommend("family", place, household, weather, lang="hi")

Inputs
------
place     = {"climate": "semi_arid", "causes": {"dark_roofs": 1.2, ...}}   # causes may be empty
household = {"roof_type": "tin", "top_floor": True, "vulnerable": True,
             "devices": ["fan", "cooler"], "cross_ventilation": False,
             "outdoor_worker": False, "has_open_ground": False,
             "budget": "low"}            # band name or an amount in rupees
weather   = {"heat_level": "high", "afternoon_rh_pct": 28}
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, variance

RULES_PATH = Path(__file__).with_name("thandak_rules.json")
TIERS = ["today", "quick", "moderate", "long"]
CATEGORIES = ["family", "colony", "government"]
HEAT_LEVELS = ["low", "moderate", "high", "extreme"]
COST_ORDER = ["free", "low", "medium", "high"]
BOOL_KEYS = ["top_floor", "vulnerable", "cross_ventilation", "outdoor_worker", "has_open_ground"]
HOUSEHOLD_KEYS = BOOL_KEYS + ["roof_type", "devices", "budget"]
TRIGGER_KEYS = {"always", "household", "min_heat_level", "area_causes"}
NUMERIC_METRICS = {"indoor_air", "outdoor_air", "heat_index"}


def load_rules(path=RULES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- inputs

def _norm_str(value):
    return value.strip().lower().replace("-", " ").replace("_", " ") if isinstance(value, str) else value


def _norm_enum(value, allowed, aliases):
    """Match case-insensitively against allowed values and aliases; None if no match."""
    v = _norm_str(value)
    if not isinstance(v, str):
        return None
    for a in allowed:
        if _norm_str(a) == v:
            return a
    for alias, target in aliases.items():
        if _norm_str(alias) == v:
            return target
    return None


def _budget_band(value):
    """Budget as a band name ('Low') or a rupee amount (4000) -> band; None if unusable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return "free"
        return "low" if value < 5000 else "medium" if value <= 50000 else "high"
    v = _norm_str(value)
    return v if v in COST_ORDER else None


def normalise_household(household, rules):
    if household is None:
        return None, []
    enums, aliases = rules["enums"], rules.get("aliases", {})
    out, warnings = {}, []
    for key, value in household.items():
        if value is None:
            continue
        if key in BOOL_KEYS:
            if isinstance(value, bool):
                out[key] = value
            else:
                warnings.append(f"household.{key}: expected true/false, got {value!r}; ignored")
        elif key == "roof_type":
            roof = _norm_enum(value, enums["roof_type"], aliases.get("roof_type", {}))
            if roof is None:
                warnings.append(f"household.roof_type: unknown value {value!r}; ignored")
            else:
                out[key] = roof
        elif key == "devices":
            items = value if isinstance(value, list) else [value]
            devices = []
            for item in items:
                if _norm_str(item) in ("none", "no", ""):
                    continue
                d = _norm_enum(item, enums["device"], aliases.get("device", {}))
                if d is None:
                    warnings.append(f"household.devices: unknown device {item!r}; ignored")
                elif d not in devices:
                    devices.append(d)
            out[key] = devices
        elif key == "budget":
            band = _budget_band(value)
            if band is None:
                warnings.append(f"household.budget: unknown value {value!r}; budget filter skipped")
            else:
                out[key] = band
        else:
            warnings.append(f"household.{key}: not used by the engine; ignored")
    return out, warnings


def normalise_weather(weather):
    weather = weather or {}
    out, warnings = {"heat_level": None, "afternoon_rh_pct": None}, []
    level = _norm_str(weather.get("heat_level"))
    if level in HEAT_LEVELS:
        out["heat_level"] = level
    elif level is not None:
        warnings.append(f"weather.heat_level: unknown value {weather.get('heat_level')!r}; ignored")
    rh = weather.get("afternoon_rh_pct")
    if isinstance(rh, (int, float)) and not isinstance(rh, bool) and 0 <= rh <= 100:
        out["afternoon_rh_pct"] = round(float(rh), 1)
    elif rh is not None:
        warnings.append(f"weather.afternoon_rh_pct: invalid value {rh!r}; ignored")
    return out, warnings


def afternoon_rh(times, rh_values, now, window=(12, 17), min_hours=3):
    """Mean forecast humidity for the next afternoon window (12:00-16:59 local by default).

    `times` are local ISO strings as Open-Meteo returns them with timezone=auto
    ("2026-05-20T13:00"); `now` is a local datetime. Uses today's window until it
    ends, then tomorrow's, so the answer doesn't change with the hour the app is opened.
    Returns None when fewer than `min_hours` forecast hours fall in the window.
    """
    start, end = window
    day = now.date() if now.hour < end else now.date() + timedelta(days=1)
    picked = []
    for t, rh in zip(times, rh_values):
        if rh is None:
            continue
        ts = datetime.fromisoformat(t)
        if ts.date() == day and start <= ts.hour < end:
            picked.append(rh)
    return round(mean(picked), 1) if len(picked) >= min_hours else None


# --------------------------------------------------------------------------- matching

def active_causes(rules, place):
    """{cause_id: degC} for area causes at or above their threshold. Negative values never count."""
    found = {}
    for cause in rules["causes"]:
        value = (place or {}).get("causes", {}).get(cause["id"])
        if not isinstance(value, (int, float)) or value <= 0:
            continue
        detect = cause["detect"]
        if value >= detect.get("shap_min_c", detect.get("min_anomaly_c", 0)):
            found[cause["id"]] = value
    return found


def _match_value(required, actual):
    if actual is None:
        return False, None
    if isinstance(required, list):
        if isinstance(actual, list):
            hit = [a for a in actual if a in required]
            return bool(hit), (hit[0] if hit else None)
        return actual in required, actual
    return actual == required, actual


def _household_reason(key, matched):
    if key == "roof_type":
        return {"code": "household.roof_type", "roof": matched}
    if key == "devices":
        return {"code": "household.device", "device": matched}
    if key == "cross_ventilation" and matched is False:
        return {"code": "household.no_cross_ventilation"}
    return {"code": f"household.{key}"}


def _trigger_matches(trigger, category, household, weather, causes):
    """(matched, reasons). All keys inside one trigger must match; any trigger in the list may match."""
    reasons = []
    if not (TRIGGER_KEYS & trigger.keys()):
        return False, []
    if "household" in trigger:
        if not household:
            return False, []
        for key, required in trigger["household"].items():
            ok, matched = _match_value(required, household.get(key))
            if not ok:
                return False, []
            reasons.append(_household_reason(key, matched))
    if "min_heat_level" in trigger:
        level = weather.get("heat_level")
        if level is None or HEAT_LEVELS.index(level) < HEAT_LEVELS.index(trigger["min_heat_level"]):
            return False, []
        reasons.append({"code": "heat_level", "level": level})
    if "area_causes" in trigger:
        if category == "family":          # area causes never trigger a family fix
            return False, []
        if not any(c in causes for c in trigger["area_causes"]):
            return False, []
    if trigger.get("always"):
        reasons.append({"code": "always"})
    return True, reasons


def _threshold(rules, value):
    return rules["thresholds"][value]["value"] if isinstance(value, str) else value


def _check_conditions(fix, rules, place, household, weather):
    """(ok, exclusion_reason, extra_reasons)."""
    cond = fix.get("conditions", {})
    if "climate" in cond and place.get("climate") not in cond["climate"]:
        return False, {"code": "climate", "climate": place.get("climate")}, []
    extra = []
    rh = weather.get("afternoon_rh_pct")
    if "max_rh_pct" in cond or "min_rh_pct" in cond:
        if rh is None:
            return False, {"code": "humidity_unknown"}, []
        if "max_rh_pct" in cond:
            limit = _threshold(rules, cond["max_rh_pct"])
            if rh > limit:
                return False, {"code": "too_humid", "rh": rh, "limit": limit}, []
            extra.append({"code": "dry_afternoon", "rh": rh})
        if "min_rh_pct" in cond:
            limit = _threshold(rules, cond["min_rh_pct"])
            if rh <= limit:
                return False, {"code": "not_humid", "rh": rh, "limit": limit}, []
            extra.append({"code": "humid_afternoon", "rh": rh})
    budget = (household or {}).get("budget")
    if budget and COST_ORDER.index(fix["cost_band"]) > COST_ORDER.index(budget):
        return False, {"code": "over_budget", "cost": fix["cost_band"], "budget": budget,
                       "subsidy_possible": bool(fix.get("subsidy_possible"))}, []
    return True, None, extra


# --------------------------------------------------------------------------- ranking & text

def _has_number(fix, cfg):
    eff = fix.get("effect") or {}
    return (eff.get("metric") in NUMERIC_METRICS and eff.get("min_c") is not None
            and eff.get("max_c") is not None and fix["evidence_level"] in cfg["numeric_evidence"])


def _score(fix, cfg, area_hit):
    if _has_number(fix, cfg):
        mid = (fix["effect"]["min_c"] + fix["effect"]["max_c"]) / 2
        effect_w, group = max(cfg["effect_weight_floor"], min(1.0, mid / cfg["effect_full_weight_c"])), 0
    else:
        effect_w, group = cfg["effect_weight_floor"], 1
    area_c = min(sum(area_hit.values()), cfg["area_bonus_cap_c"])
    score = (effect_w * cfg["evidence_weight"][fix["evidence_level"]]
             * cfg["cost_weight"][fix["cost_band"]] * (1 + cfg["area_bonus_per_c"] * area_c))
    return group, round(score, 3)


def _num(x):
    return f"{x:g}"


def _label(table, code, lang, **params):
    entry = table.get(code)
    if not entry:
        return code
    return (entry.get(lang) or entry["en"]).format(**params)


def _reason_text(reason, rules, lang):
    labels, values = rules["labels"]["reason"], rules["labels"]["value"]
    p = {}
    if "level" in reason:
        p["level"] = values["heat_level"][reason["level"]].get(lang, reason["level"])
    if "roof" in reason:
        p["roof"] = values["roof_type"][reason["roof"]].get(lang, reason["roof"])
    if "device" in reason:
        p["device"] = values["device"][reason["device"]].get(lang, reason["device"])
    if "rh" in reason:
        p["rh"] = _num(reason["rh"])
    if reason["code"] == "area_cause":
        p["cause"] = reason["label"]
        p["c"] = _num(reason["c"])
    return _label(labels, reason["code"], lang, **p)


def _effect_out(fix, rules, lang):
    cfg, labels = rules["ranking"], rules["labels"]["effect"]
    eff = fix.get("effect") or {}
    lo, hi = eff.get("min_c"), eff.get("max_c")
    if eff.get("metric") == "exposure":
        kind = "exposure"
    elif _has_number(fix, cfg):
        kind = eff["metric"]
    elif lo is not None and hi is not None and fix["evidence_level"] == "review":
        kind = "global_only"
    else:
        kind = "unmeasured_family" if fix["category"] == "family" else "unmeasured"
    shown = kind in NUMERIC_METRICS
    out = {"kind": kind, "evidence": fix["evidence_level"],
           "min_c": lo if shown else None, "max_c": hi if shown else None,
           "text": _label(labels, kind, lang, lo=_num(lo) if shown else "", hi=_num(hi) if shown else "")}
    note = eff.get(f"note_{lang}") or eff.get("note")
    if note:
        out["note"] = note
    return out


def _localised(fix, field, lang, missing):
    """Field in the requested language, else English (title_en or the bare field); records the fallback."""
    english = fix.get(f"{field}_en") or fix.get(field)
    if lang != "en":
        value = fix.get(f"{field}_{lang}")
        if value:
            return value
        if english:
            missing.add(fix["id"])
    return english


# --------------------------------------------------------------------------- main entry

def recommend(category, place=None, household=None, weather=None, rules=None, lang="en"):
    """Personalised fixes grouped by tier, plus fixes left out and why."""
    rules = rules or load_rules()
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}, got {category!r}")
    if lang not in ("en", "hi"):
        raise ValueError(f"lang must be 'en' or 'hi', got {lang!r}")
    cfg = rules["ranking"]
    place = place or {}
    household, warnings = normalise_household(household, rules)
    weather, w2 = normalise_weather(weather)
    warnings += w2
    if category != "family":
        household = None
    causes = active_causes(rules, place)
    cause_label = {c["id"]: c.get(f"label_{lang}") or c["label_en"] for c in rules["causes"]}
    missing = set()

    shown = {t: [] for t in TIERS}
    excluded = []
    for fix in rules["fixes"]:
        if fix["category"] != category:
            continue
        matched, reasons = False, []
        for trig in fix.get("triggers", []):
            ok, why = _trigger_matches(trig, category, household, weather, causes)
            if ok:
                matched = True
                reasons += [r for r in why if r not in reasons]
        if not matched:
            continue
        title = _localised(fix, "title", lang, missing)
        ok, block, extra = _check_conditions(fix, rules, place, household, weather)
        if not ok:
            if block["code"] != "not_humid":
                excluded.append({"id": fix["id"], "tier": fix["tier"], "title": title,
                                 "variant_group": fix.get("variant_group"), "reason": block})
            continue
        area_hit = {c: causes[c] for c in fix.get("addresses", []) if c in causes}
        group, score = _score(fix, cfg, area_hit)
        order = 0
        if fix["tier"] == "today":
            group, order = cfg["today_group_order"].index(fix["rank_group"]), fix.get("order", 99)
        because = reasons + extra + [
            {"code": "area_cause", "cause": c, "label": cause_label[c], "c": v}
            for c, v in sorted(area_hit.items(), key=lambda kv: -kv[1])]
        for r in because:
            r["text"] = _reason_text(r, rules, lang)
        shown[fix["tier"]].append({
            "id": fix["id"], "tier": fix["tier"], "title": title,
            "group": group, "order": order, "score": score,
            "because": because,
            "effect": _effect_out(fix, rules, lang),
            "cost": fix["cost_band"],
            "steps": _localised(fix, "steps", lang, missing) or [],
            "caution": _localised(fix, "avoid_if", lang, missing),
            "variant_group": fix.get("variant_group"),
            "sources": [{"id": s, "title": rules["sources"][s]["title"], "url": rules["sources"][s].get("url")}
                        for s in fix.get("source_ids", [])],
        })
        if lang != "en" and (fix.get("effect") or {}).get("note") and not fix["effect"].get(f"note_{lang}"):
            missing.add(fix["id"])

    shown_variants = {f["variant_group"] for t in TIERS for f in shown[t] if f["variant_group"]}
    excluded = [e for e in excluded if not (e["variant_group"] and e["variant_group"] in shown_variants)]
    for e in excluded:
        r = e.pop("reason")
        code = r["code"]
        if code == "over_budget" and r["subsidy_possible"]:
            code = "over_budget_subsidy"
        e["reason"] = {**r, "text": _label(rules["labels"]["excluded"], code, lang,
                                           rh=_num(r["rh"]) if "rh" in r else "")}
        e.pop("variant_group")

    for tier in TIERS:
        shown[tier].sort(key=lambda f: (f["group"], f["order"], -f["score"], f["id"]))
        shown[tier] = shown[tier][: cfg["max_per_tier"][tier]]
        for f in shown[tier]:
            f.pop("variant_group")
            f.pop("order")

    result = {
        "category": category,
        "lang": lang,
        "inputs": {"heat_level": weather["heat_level"], "afternoon_rh_pct": weather["afternoon_rh_pct"],
                   "has_area_profile": bool(place.get("causes"))},
        "active_causes": causes,
        "fixes": shown,
        "excluded": excluded,
        "warnings": warnings,
        "needs_translation": sorted(missing),
    }
    if category == "family":
        result["fan_profile"] = "vulnerable" if (household or {}).get("vulnerable") else "standard"
    return result


# --------------------------------------------------------------------------- before/after readings

def estimate_fix_effect(before, after, min_days=3, min_half_width_c=0.5):
    """Effect of a fix from a home's own thermometer readings.

    `before` / `after`: one reading per day at the same clock time, e.g.
    {"indoor_c": 37.5, "outdoor_c": 41.0}. Compares the indoor-minus-outdoor gap,
    so a hotter or cooler week after the fix doesn't hide or fake its effect.
    effect_c > 0 means the home now runs cooler relative to outside. The range is
    never narrower than +/- min_half_width_c, because cheap thermometers and grid
    forecasts can't support more precision than that.
    """
    def gaps(rows):
        return [r["indoor_c"] - r["outdoor_c"] for r in rows
                if isinstance(r.get("indoor_c"), (int, float)) and isinstance(r.get("outdoor_c"), (int, float))]

    gb, ga = gaps(before), gaps(after)
    if len(gb) < min_days or len(ga) < min_days:
        return {"status": "need_more_readings", "have": {"before": len(gb), "after": len(ga)}, "need": min_days}
    effect = mean(gb) - mean(ga)
    se = math.sqrt(variance(gb) / len(gb) + variance(ga) / len(ga))
    half = max(2 * se, min_half_width_c)
    return {"status": "ok", "effect_c": round(effect, 1),
            "range_c": [round(effect - half, 1), round(effect + half, 1)],
            "days": {"before": len(gb), "after": len(ga)},
            "label": "measured_in_this_home"}


# --------------------------------------------------------------------------- rules check

def validate_rules(rules):
    """{"errors": [...must fix...], "warnings": [...track before launch...]}"""
    errors, warnings = [], []
    enums, cfg = rules["enums"], rules["ranking"]
    causes = {c["id"] for c in rules["causes"]}
    seen = set()
    for f in rules["fixes"]:
        fid = f.get("id", "?")
        if fid in seen:
            errors.append(f"{fid}: duplicate id")
        seen.add(fid)
        checks = [("category", CATEGORIES), ("tier", TIERS), ("cost_band", list(enums["cost_band"])),
                  ("evidence_level", list(enums["evidence_level"]))]
        for key, allowed in checks:
            if f.get(key) not in allowed:
                errors.append(f"{fid}: {key}={f.get(key)!r} not in {allowed}")
        if f.get("evidence_level") not in cfg["evidence_weight"]:
            errors.append(f"{fid}: no evidence_weight for {f.get('evidence_level')!r}")
        if f.get("tier") == "today" and f.get("rank_group") not in cfg["today_group_order"]:
            errors.append(f"{fid}: today-tier fix needs rank_group in {cfg['today_group_order']}")
        for c in f.get("addresses", []):
            if c not in causes:
                errors.append(f"{fid}: unknown cause {c!r}")
        for s in f.get("source_ids", []):
            if s not in rules["sources"]:
                errors.append(f"{fid}: unknown source {s!r}")
        if not f.get("triggers"):
            errors.append(f"{fid}: no triggers")
        for t in f.get("triggers", []):
            if not t or set(t) - TRIGGER_KEYS:
                errors.append(f"{fid}: bad trigger {t}")
            if f.get("category") == "family" and "area_causes" in t:
                errors.append(f"{fid}: family fixes can't be triggered by area causes")
            if "min_heat_level" in t and t["min_heat_level"] not in HEAT_LEVELS:
                errors.append(f"{fid}: unknown heat level {t['min_heat_level']!r}")
            for c in t.get("area_causes", []):
                if c not in causes:
                    errors.append(f"{fid}: unknown trigger cause {c!r}")
            for k, v in t.get("household", {}).items():
                if k not in HOUSEHOLD_KEYS:
                    errors.append(f"{fid}: unknown household key {k!r}")
                if k == "roof_type" and set(v) - set(enums["roof_type"]):
                    errors.append(f"{fid}: unknown roof type in {v}")
        for k in ("max_rh_pct", "min_rh_pct"):
            v = f.get("conditions", {}).get(k)
            if isinstance(v, str) and v not in rules.get("thresholds", {}):
                errors.append(f"{fid}: unknown threshold {v!r}")
        eff = f.get("effect") or {}
        if eff.get("min_c") is not None and not f.get("source_ids"):
            errors.append(f"{fid}: effect number without a source")
        if not f.get("source_ids"):
            warnings.append(f"{fid}: no source yet (link one or hold the fix back before launch)")
        for field in ("title", "steps", "avoid_if"):
            if f.get(field) and not f.get(f"{field}_hi"):
                warnings.append(f"{fid}: missing {field}_hi")
        if eff.get("note") and not eff.get("note_hi"):
            warnings.append(f"{fid}: missing effect.note_hi")
    for sid, s in rules["sources"].items():
        if not s.get("url"):
            warnings.append(f"source {sid}: no URL yet ({s.get('status', 'missing')})")
    for name, t in rules.get("thresholds", {}).items():
        if t.get("status") not in ("verified", "design_choice"):
            warnings.append(f"threshold {name}={t.get('value')}: {t.get('status')}")
    warnings.append("cost bands: rough estimates, verify against local prices")
    return {"errors": errors, "warnings": warnings}


# --------------------------------------------------------------------------- demo

def _print(title, out):
    print(f"\n=== {title} ===")
    print(f"inputs: {out['inputs']}" + (f"   fan_profile: {out['fan_profile']}" if "fan_profile" in out else ""))
    for tier in TIERS:
        if out["fixes"][tier]:
            print(f"  [{tier.upper()}]")
        for f in out["fixes"][tier]:
            print(f"    - {f['title']}")
            print(f"        because: {'; '.join(r['text'] for r in f['because'])}")
            print(f"        effect:  {f['effect']['text']}  [{f['effect']['evidence']}, cost: {f['cost']}]")
    for e in out["excluded"]:
        print(f"  left out: {e['title']} -> {e['reason']['text']}")
    if out["warnings"]:
        print("  warnings:", out["warnings"])
    if out["needs_translation"]:
        print("  needs_translation:", ", ".join(out["needs_translation"]))


if __name__ == "__main__":
    rules = load_rules()
    tilawala = {"climate": "semi_arid",
                "causes": {"dark_roofs": 1.2, "bare_paved_ground": 0.9, "low_tree_cover": 0.5, "night_heat": 1.3}}
    family = {"roof_type": "tin", "top_floor": True, "vulnerable": True, "devices": ["fan", "cooler"],
              "cross_ventilation": False, "outdoor_worker": True, "has_open_ground": False, "budget": "low"}
    high_dry = {"heat_level": "high", "afternoon_rh_pct": 24}

    _print("Family, Tilawala Jaipur: tin roof, top floor, elderly parent, fan + cooler, High day",
           recommend("family", tilawala, family, high_dry, rules))
    _print("Same family, village with no satellite profile",
           recommend("family", {"climate": "semi_arid"}, family, high_dry, rules))
    _print("Family in a humid city, cooler at home, 72% afternoon humidity",
           recommend("family", {"climate": "humid"}, {"devices": ["cooler", "fan"], "top_floor": False},
                     {"heat_level": "high", "afternoon_rh_pct": 72}, rules))
    _print("Colony on a High day, no hot-night anomaly",
           recommend("colony", {"climate": "semi_arid", "causes": {"dark_roofs": 0.8}}, None, high_dry, rules))
    _print("Hindi: same Tilawala family",
           recommend("family", tilawala, family, high_dry, rules, lang="hi"))
    report = validate_rules(rules)
    print(f"\nrules check: {len(report['errors'])} errors, {len(report['warnings'])} warnings")
