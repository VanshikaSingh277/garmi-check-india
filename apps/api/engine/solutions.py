"""Fix recommendations (data/fixes.json, the one catalogue). Ported from the v2 reference engine (reference/thandak_v2).

A fix appears when one of its triggers matches and its conditions hold:
- family fixes are triggered by the household's answers and today's heat level only; area causes (satellite) can raise
  a fix's rank and add a "because" line but never trigger or block one, so a village with no satellite data gets full advice
- colony / government fixes are also triggered by area causes; where a place has no area profile yet, those fixes are
  offered as common fixes instead of disappearing
Everything filtered out by a condition (roof, roof access, budget, afternoon wet-bulb, climate, unverified evidence) comes back in
"excluded" with a reason. Effect numbers come only from verified_numbers.csv (effect.key); nothing unverified is shown
as a fact. Each fix carries the reasons it was chosen ("because")."""
import json
import math
import os
import re
from datetime import datetime, timedelta
from functools import lru_cache
from statistics import mean, variance

from . import verified as V

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fixes.json")
TIERS = ["today", "quick", "moderate", "long", "avoid"]
CATEGORIES = ["family", "colony", "government"]
HEAT_LEVELS = ["low", "moderate", "high", "extreme"]
COST_ORDER = ["free", "low", "medium", "high"]
BOOL_KEYS = ["top_floor", "vulnerable", "cross_ventilation", "outdoor_worker", "has_open_ground", "roof_access"]
HOUSEHOLD_KEYS = BOOL_KEYS + ["roof_type", "devices", "budget"]
TRIGGER_KEYS = {"always", "household", "min_heat_level", "area_causes"}
NUMERIC_METRICS = {"indoor_air", "outdoor_air", "heat_index"}
# a number inside a sentence: {n:<verified_numbers key>:<field>:<decimals>} (spec §2 rule 2)
NUMBER = re.compile(r"\{n:([A-Za-z0-9_.]+):([A-Za-z0-9_]+):(\d)\}")


def fill_numbers(text):
    """Replace each {n:key:field:decimals} with the number from verified_numbers.csv (Verified or Computed rows only)."""
    if isinstance(text, list):
        return [fill_numbers(t) for t in text]
    if not isinstance(text, str):
        return text

    def one(m):
        key, field, dec = m.group(1), m.group(2), int(m.group(3))
        if not V.shown_ok(key):
            raise ValueError(f"{key} is {V.table()[key]['status']!r}: not shown to users as a fact")
        return f"{float(V.value(key)[field]):.{dec}f}"
    return NUMBER.sub(one, text)


@lru_cache(maxsize=1)
def catalogue(path: str = PATH) -> dict:
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


def budget_band(value):
    """Budget as a band name ('Low') or a rupee amount (4000) -> band; None if unusable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        lim = V.value(catalogue()["budget"]["key"])
        if value <= 0:
            return "free"
        return "low" if value < lim["low_below"] else "medium" if value <= lim["medium_upto"] else "high"
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
            band = budget_band(value)
            if band is None:
                warnings.append(f"household.budget: unknown value {value!r}; budget filter skipped")
            else:
                out[key] = band
        else:
            warnings.append(f"household.{key}: not used by the engine; ignored")
    return out, warnings


def normalise_weather(weather):
    weather = weather or {}
    out, warnings = {"heat_level": None, "afternoon_rh_pct": None, "afternoon_twb_c": None}, []
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
    twb = weather.get("afternoon_twb_c")
    if isinstance(twb, (int, float)) and not isinstance(twb, bool) and -10 <= twb <= 40:
        out["afternoon_twb_c"] = round(float(twb), 1)
    elif twb is not None:
        warnings.append(f"weather.afternoon_twb_c: invalid value {twb!r}; ignored")
    return out, warnings


def afternoon_mean(times, values, now, window=None, min_hours=3):
    """Mean of a forecast variable (humidity, wet-bulb) over the next afternoon window (12:00-16:59 local by default).

    `times` are local ISO strings ("2026-05-20T13:00"); `now` is a local datetime (Asia/Kolkata). Uses today's window
    until it ends, then tomorrow's, so the answer doesn't change with the hour the app is opened.
    Returns None when fewer than `min_hours` forecast hours fall in the window."""
    start, end = window or catalogue()["thresholds"]["afternoon_window_hours"]["value"]
    day = now.date() if now.hour < end else now.date() + timedelta(days=1)
    picked = []
    for t, x in zip(times, values, strict=False):
        if x is None:
            continue
        ts = datetime.fromisoformat(t)
        if ts.date() == day and start <= ts.hour < end:
            picked.append(x)
    return round(mean(picked), 1) if len(picked) >= min_hours else None


afternoon_rh = afternoon_mean


def climate_of(district_heat):
    """Climate type from the district's summer dryness (daily max air temperature minus daily max wet-bulb)."""
    if not district_heat or district_heat.get("tmax_mean_c") is None or district_heat.get("twb_max_mean_c") is None:
        return None
    c = V.value(catalogue()["climate"]["key"])
    dep = district_heat["tmax_mean_c"] - district_heat["twb_max_mean_c"]
    return "arid" if dep >= c["arid_min"] else "semi_arid" if dep >= c["semi_arid_min"] else "tropical_savanna" if dep >= c["tropical_savanna_min"] else "humid"


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


def _trigger_matches(trigger, category, household, weather, causes, has_profile):
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
        if not has_profile:               # no satellite profile here yet: offer it as a common fix
            reasons.append({"code": "no_area_profile"})
        elif not any(c in causes for c in trigger["area_causes"]):
            return False, []
    if trigger.get("always"):
        reasons.append({"code": "always"})
    return True, reasons


def _threshold(rules, name):
    t = rules["thresholds"][name]
    return V.value(t["key"])[t["field"]] if "key" in t else t["value"]


def _effect_range(fix):
    """(lo, hi) from verified_numbers.csv for a numeric effect, else (None, None)."""
    eff = fix.get("effect") or {}
    if eff.get("metric") not in NUMERIC_METRICS or not eff.get("key") or not eff.get("range"):
        return None, None
    v = V.value(eff["key"])
    return v[eff["range"][0]], v[eff["range"][1]]


def _check_conditions(fix, rules, place, household, weather):
    """(ok, exclusion_reason, extra_reasons)."""
    cond, hh, extra = fix.get("conditions", {}), household or {}, []
    if "climate" in cond:
        if not place.get("climate"):          # unknown climate fails: dense and sparse tree advice must never show together
            return False, {"code": "climate_unknown"}, []
        if place["climate"] not in cond["climate"]:
            return False, {"code": "climate", "climate": place["climate"]}, []
    if "roof_type" in cond and hh.get("roof_type") and hh["roof_type"] not in cond["roof_type"]:
        return False, {"code": "roof_mismatch", "roof": hh["roof_type"]}, []
    if cond.get("requires_roof_access"):
        if hh.get("roof_access") is False:
            return False, {"code": "no_roof_access"}, []
        if hh.get("roof_access"):
            extra.append({"code": "household.roof_access"})
    eff = fix.get("effect") or {}
    if eff.get("key") and not V.usable(eff["key"]):
        return False, {"code": "evidence_not_verified"}, []
    # evaporative cooling can only reach the wet-bulb temperature, so the afternoon wet-bulb decides (not % humidity)
    twb = weather.get("afternoon_twb_c")
    if "max_twb_c" in cond or "min_twb_c" in cond:
        t = rules["thresholds"][cond.get("max_twb_c") or cond.get("min_twb_c")]
        if "key" in t and not V.rule_ok(t["key"]):     # spec §7.5: off until the threshold is verified
            return False, {"code": "threshold_not_verified"}, []
        if twb is None:
            return False, {"code": "humidity_unknown"}, []
        if "max_twb_c" in cond:
            if twb > _threshold(rules, cond["max_twb_c"]):
                return False, {"code": "too_humid", "twb": twb}, []
            extra.append({"code": "dry_afternoon", "twb": twb})
        if "min_twb_c" in cond:
            if twb <= _threshold(rules, cond["min_twb_c"]):
                return False, {"code": "not_humid", "twb": twb}, []
            extra.append({"code": "humid_afternoon", "twb": twb})
    budget = hh.get("budget")
    if budget and COST_ORDER.index(fix["cost_band"]) > COST_ORDER.index(budget):
        return False, {"code": "over_budget", "cost": fix["cost_band"], "budget": budget,
                       "subsidy_possible": bool(fix.get("subsidy_possible"))}, []
    return True, None, extra


# --------------------------------------------------------------------------- ranking & text

def _has_number(fix, cfg):
    lo, hi = _effect_range(fix)
    return lo is not None and hi is not None and fix["evidence_level"] in cfg["numeric_evidence"]


def _score(fix, cfg, area_hit):
    if _has_number(fix, cfg):
        lo, hi = _effect_range(fix)
        effect_w, group = max(cfg["effect_weight_floor"], min(1.0, (lo + hi) / 2 / cfg["effect_full_weight_c"])), 0
    else:
        effect_w, group = cfg["effect_weight_floor"], 1
    area_c = min(sum(area_hit.values()), cfg["area_bonus_cap_c"])
    if fix.get("evidence_n") == 1:          # a number from one home is weak evidence: it shouldn't outrank a replicated one
        effect_w *= cfg.get("single_home_factor", 1.0)
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
    if "twb" in reason:
        p["twb"] = _num(reason["twb"])
    if reason["code"] == "area_cause":
        p["cause"] = reason["label"]
        p["c"] = _num(reason["c"])
    return _label(labels, reason["code"], lang, **p)


def _effect_kind(fix, cfg):
    eff = fix.get("effect") or {}
    if eff.get("metric") in ("exposure", "context", "harm"):
        return eff["metric"]
    if _has_number(fix, cfg):
        return eff["metric"]
    if eff.get("kind") == "global_only":
        return "global_only"
    if fix["evidence_level"] == "qualitative" and not fix.get("source_ids"):
        return "general"
    return "unmeasured_family" if "family" in fix["categories"] else "unmeasured"


def _effect_out(fix, rules, lang):
    cfg, labels = rules["ranking"], rules["labels"]["effect"]
    eff = fix.get("effect") or {}
    kind = _effect_kind(fix, cfg)
    lo, hi = _effect_range(fix) if kind in NUMERIC_METRICS else (None, None)
    own = fill_numbers(fix.get(f"effect_text_{lang}") or fix.get("effect_text_en"))
    out = {"kind": kind, "evidence": fix["evidence_level"], "min_c": lo, "max_c": hi,
           "text": own or _label(labels, kind, lang, lo=_num(lo) if lo is not None else "", hi=_num(hi) if hi is not None else "")}
    note = eff.get(f"note_{lang}") or eff.get("note_en")
    if note:
        out["note"] = note
    if eff.get("key"):
        out["status"] = V.table()[eff["key"]]["status"]
    return out


def _localised(fix, field, lang, missing):
    """Field in the requested language, else English; records the fallback."""
    english = fix.get(f"{field}_en")
    if lang != "en":
        value = fix.get(f"{field}_{lang}")
        if value:
            return fill_numbers(value)
        if english:
            missing.add(fix["id"])
    return fill_numbers(english)


def _caution(fix, household, lang, missing):
    """The fix's own caution plus any that apply to this home (e.g. asbestos sheets), as one text."""
    parts = [_localised(fix, "avoid_if", lang, missing)]
    roof = (household or {}).get("roof_type")
    for c in fix.get("cautions", []):
        if "roof_type" not in c or roof in c["roof_type"]:
            if lang != "en" and not c.get(lang):
                missing.add(fix["id"])
            parts.append(fill_numbers(c.get(lang) or c["en"]))
    return " ".join(p for p in parts if p) or None


def _sources(fix, rules):
    out = [{"id": s, "title": rules["sources"][s]["title"], "url": rules["sources"][s].get("url")} for s in fix.get("source_ids", [])]
    key = (fix.get("effect") or {}).get("key")
    if key:
        src = V.source(key)
        if src["url"] and all(src["url"] != s["url"] for s in out):
            out.append({"id": key, "title": src["title"], "url": src["url"]})
    return out


# --------------------------------------------------------------------------- main entry

def recommend(category, place=None, household=None, weather=None, lang="en", rules=None):
    """Personalised fixes grouped by tier, plus fixes left out and why."""
    rules = rules or catalogue()
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
    has_profile = bool(place.get("causes"))
    cause_label = {c["id"]: c.get(f"label_{lang}") or c["label_en"] for c in rules["causes"]}
    missing = set()

    shown = {t: [] for t in TIERS}
    excluded = []
    for fix in rules["fixes"]:
        if category not in fix["categories"]:
            continue
        matched, reasons = False, []
        for trig in fix.get("triggers", []):
            ok, why = _trigger_matches(trig, category, household, weather, causes, has_profile)
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
        if fix["tier"] == "avoid":
            extra = extra + [{"code": "avoid_harm"}]
        because = reasons + extra + [
            {"code": "area_cause", "cause": c, "label": cause_label[c], "c": v}
            for c, v in sorted(area_hit.items(), key=lambda kv: -kv[1])]
        for r in because:
            r["text"] = _reason_text(r, rules, lang)
        ck = fix.get("cost_key")
        shown[fix["tier"]].append({
            "id": fix["id"], "tier": fix["tier"], "title": title,
            "group": group, "order": order, "score": score,
            "because": because,
            "effect": _effect_out(fix, rules, lang),
            "cost": fix["cost_band"],
            "cost_text": _localised(fix, "cost_text", lang, missing),
            "cost_status": V.table()[ck]["status"] if ck else "",
            "time": _localised(fix, "time", lang, missing), "who": _localised(fix, "who", lang, missing),
            "steps": _localised(fix, "steps", lang, missing) or [],
            "caution": _caution(fix, household, lang, missing),
            "variant_group": fix.get("variant_group"),
            "sources": _sources(fix, rules),
        })
        if lang != "en" and (fix.get("effect") or {}).get("note_en") and not fix["effect"].get(f"note_{lang}"):
            missing.add(fix["id"])

    shown_variants = {f["variant_group"] for t in TIERS for f in shown[t] if f["variant_group"]}
    excluded = [e for e in excluded if not (e["variant_group"] and e["variant_group"] in shown_variants)]
    seen_variants = set()                       # both variants left out for one reason: list the group once
    excluded = [e for e in excluded if not e["variant_group"] or not (e["variant_group"] in seen_variants or seen_variants.add(e["variant_group"]))]
    for e in excluded:
        r = e.pop("reason")
        code = r["code"]
        if code == "over_budget" and r["subsidy_possible"]:
            code = "over_budget_subsidy"
        e["reason"] = {**r, "text": _label(rules["labels"]["excluded"], code, lang, rh=_num(r["rh"]) if "rh" in r else "",
                                           twb=_num(r["twb"]) if "twb" in r else "")}
        e.pop("variant_group")

    for tier in TIERS:
        shown[tier].sort(key=lambda f: (f["group"], f["order"], -f["score"], f["id"]))
        shown[tier] = shown[tier][: cfg["max_per_tier"][tier]]
        for f in shown[tier]:
            f.pop("variant_group")
            f.pop("order")

    result = {
        "category": category, "lang": lang,
        "inputs": {"heat_level": weather["heat_level"], "afternoon_rh_pct": weather["afternoon_rh_pct"],
                   "afternoon_twb_c": weather["afternoon_twb_c"],
                   "climate": place.get("climate"), "has_area_profile": has_profile},
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

    `before` / `after`: one reading per day at the same clock time, e.g. {"indoor_c": 37.5, "outdoor_c": 41.0}.
    Compares the indoor-minus-outdoor gap, so a hotter or cooler week after the fix doesn't hide or fake its effect.
    effect_c > 0 means the home now runs cooler relative to outside. The range is never narrower than
    +/- min_half_width_c, because cheap thermometers and grid forecasts can't support more precision than that."""
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


# --------------------------------------------------------------------------- catalogue check

def _all_text(fix):
    for k, v in fix.items():
        if k.endswith(("_en", "_hi")):
            yield from (v if isinstance(v, list) else [v])
    for c in fix.get("cautions", []):
        yield from (c.get("en", ""), c.get("hi", ""))


def validate_rules(rules=None):
    """{"errors": [...must fix...], "warnings": [...track before launch...]}"""
    rules = rules or catalogue()
    errors, warnings = [], []
    enums, cfg = rules["enums"], rules["ranking"]
    causes = {c["id"] for c in rules["causes"]}
    table = V.table()
    seen = set()
    for f in rules["fixes"]:
        fid = f.get("id", "?")
        if fid in seen:
            errors.append(f"{fid}: duplicate id")
        seen.add(fid)
        if not f.get("categories") or set(f["categories"]) - set(CATEGORIES):
            errors.append(f"{fid}: categories={f.get('categories')!r} not in {CATEGORIES}")
        for key, allowed in (("tier", TIERS), ("cost_band", list(enums["cost_band"])), ("evidence_level", list(enums["evidence_level"]))):
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
            if "family" in f.get("categories", []) and "area_causes" in t:
                errors.append(f"{fid}: family fixes can't be triggered by area causes")
            if "min_heat_level" in t and t["min_heat_level"] not in HEAT_LEVELS:
                errors.append(f"{fid}: unknown heat level {t['min_heat_level']!r}")
            for c in t.get("area_causes", []):
                if c not in causes:
                    errors.append(f"{fid}: unknown trigger cause {c!r}")
            for k in t.get("household", {}):
                if k not in HOUSEHOLD_KEYS:
                    errors.append(f"{fid}: unknown household key {k!r}")
        for r in f.get("conditions", {}).get("roof_type", []):
            if r not in enums["roof_type"]:
                errors.append(f"{fid}: unknown roof type {r!r}")
        for c in f.get("cautions", []):
            if not c.get("en") or not c.get("hi"):
                errors.append(f"{fid}: caution needs en and hi")
            for r in c.get("roof_type", []):
                if r not in enums["roof_type"]:
                    errors.append(f"{fid}: caution for unknown roof type {r!r}")
        for k in ("max_twb_c", "min_twb_c"):
            v = f.get("conditions", {}).get(k)
            if v is not None and v not in rules.get("thresholds", {}):
                errors.append(f"{fid}: unknown threshold {v!r}")
        eff = f.get("effect") or {}
        if eff.get("key") and eff["key"] not in table:
            errors.append(f"{fid}: effect key {eff['key']!r} not in verified_numbers.csv")
        if eff.get("metric") in NUMERIC_METRICS and eff.get("range") and eff.get("key") in table:
            v = table[eff["key"]]["value_parsed"] or {}
            if any(r not in v for r in eff["range"]):
                errors.append(f"{fid}: effect range {eff['range']} not in {eff['key']}")
        if f.get("cost_key") and f["cost_key"] not in table:
            errors.append(f"{fid}: cost key {f['cost_key']!r} not in verified_numbers.csv")
        for field_text in _all_text(f):
            for m in NUMBER.finditer(field_text):
                key, field = m.group(1), m.group(2)
                if key not in table:
                    errors.append(f"{fid}: number {m.group(0)} uses unknown key {key!r}")
                elif not isinstance(table[key]["value_parsed"], dict) or field not in table[key]["value_parsed"]:
                    errors.append(f"{fid}: number {m.group(0)}: no field {field!r} in {key}")
                elif not V.shown_ok(key):
                    errors.append(f"{fid}: number {m.group(0)} comes from {key} ({table[key]['status']}), not Verified/Computed")
        if not f.get("source_ids") and not eff.get("key"):
            warnings.append(f"{fid}: no source yet (shown as general advice)")
        for field in ("title", "steps", "avoid_if", "effect_text", "cost_text", "time", "who"):
            if f.get(f"{field}_en") and not f.get(f"{field}_hi"):
                warnings.append(f"{fid}: missing {field}_hi")
        if eff.get("note_en") and not eff.get("note_hi"):
            warnings.append(f"{fid}: missing effect.note_hi")
    for sid, s in rules["sources"].items():
        if not s.get("url"):
            warnings.append(f"source {sid}: no URL yet")
    for name, t in rules.get("thresholds", {}).items():
        if "key" in t:
            if t["key"] not in table:
                errors.append(f"threshold {name}: key {t['key']!r} not in verified_numbers.csv")
            elif not V.usable(t["key"]):
                warnings.append(f"threshold {name} ({t['key']}): {table[t['key']]['status']}")
    for name in ("climate", "budget"):
        k = rules[name]["key"]
        if k not in table:
            errors.append(f"{name}: key {k!r} not in verified_numbers.csv")
        elif not V.usable(k):
            warnings.append(f"{name} ({k}): {table[k]['status']}")
    return {"errors": errors, "warnings": warnings}
