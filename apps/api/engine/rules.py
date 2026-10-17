"""Risk level + fan advice. Every threshold is read from verified_numbers (see engine/verified.py).
Levels: 0 Low, 1 Moderate, 2 High, 3 Extreme. Each raise carries a reason code so the UI/AI can explain why."""
from . import verified as V

LEVELS = ["low", "moderate", "high", "extreme"]


def base_from_heat_index(hi_max: float) -> int:
    b = V.value("heat_index.bands.imd")            # IMD experimental heat index (PIB 2023)
    # gaps in the source (35-36, 45-46) are resolved upward (stricter)
    if hi_max > b["red_above"]:
        return 3
    if hi_max > b["yellow"][1]:
        return 2
    if hi_max >= b["green_below"]:
        return 1
    return 0


def risk(next24: list, today: list, tomorrow: list, roof: str, vulnerable: list, devices: dict, indoor_peak: float = None,
         in_delhi: bool = False) -> dict:
    """India-wide: IMD heat-index bands, IMD actual-Tmax heat-wave rule (>= 45 C) and the wet-bulb danger limit.
    Delhi only: the Delhi HAP two-day 97th-percentile rule (its threshold was derived from Delhi data).
    indoor_peak: predicted indoor temperature peak (degC). Household raises (roof / person / no cooling) apply only
    when there is real heat: outdoor heat index or indoor peak >= the 35 degC 'fan alone not enough' limit
    (decision 2026-10-15, avoids calling a mild day 'High' just because of household factors)."""
    reasons = []
    hi_max = max(r["hi"] for r in next24)
    twb_max = max(r["twb"] for r in next24)
    tmax = max(r["t"] for r in next24)
    lvl = base_from_heat_index(hi_max)
    reasons.append({"code": "base_heat_index", "value": round(hi_max, 1), "level": LEVELS[lvl], "source": V.source("heat_index.bands.imd")})
    hw = V.value("imd.heatwave")
    if tmax >= hw["hw_actual_tmax"] and lvl < 2:
        lvl = 2
        reasons.append({"code": "heatwave_tmax", "value": round(tmax, 1), "source": V.source("imd.heatwave")})
    p97 = V.value("delhi.heatwave.p97_daily_mean")["p97"]
    means = [sum(r["t"] for r in d) / len(d) for d in (today, tomorrow) if d]
    if in_delhi and len(means) == 2 and all(m > p97 for m in means) and lvl < 2:
        lvl = 2
        reasons.append({"code": "heatwave_p97", "value": [round(m, 1) for m in means], "threshold": p97, "source": V.source("delhi.heatwave.p97_daily_mean")})
    wb = V.value("wet_bulb.danger")
    if twb_max >= wb["critical_humid_young_mean"]:
        lvl = 3
        reasons.append({"code": "wet_bulb_critical", "value": round(twb_max, 1), "source": V.source("wet_bulb.danger")})
    raises = []
    heat_gate = V.value("fan.limit.older")["fan_alone_not_enough_above"]
    hot_enough = hi_max >= heat_gate or (indoor_peak is not None and indoor_peak >= heat_gate)
    if not hot_enough:
        reasons.append({"code": "no_household_raise_mild_heat", "threshold": heat_gate})
        return {"level": LEVELS[lvl], "level_index": lvl, "reasons": reasons, "hi_max": round(hi_max, 1), "twb_max": round(twb_max, 1), "tmax": round(tmax, 1)}
    if roof == "tin_top":
        raises.append("tin_roof_top_floor")
    if vulnerable:
        raises.append("vulnerable_person")
    if not (devices.get("fan") or devices.get("cooler") or devices.get("ac")):
        raises.append("no_cooling")
    for code in raises:
        if lvl < 3:
            lvl += 1
        reasons.append({"code": code, "raise": 1})
    return {"level": LEVELS[lvl], "level_index": lvl, "reasons": reasons, "hi_max": round(hi_max, 1), "twb_max": round(twb_max, 1), "tmax": round(tmax, 1)}


def fan_limits(group: str) -> dict:
    if group == "older":
        o = V.value("fan.limit.older")
        return {"not_enough_from": o["fan_alone_not_enough_above"], "avoid_from": o["fan_detrimental_above"], "key": "fan.limit.older"}
    h = V.value("fan.limit.healthy")
    return {"not_enough_from": V.value("fan.limit.older")["fan_alone_not_enough_above"],   # Meade 2024: >35 C no meaningful core cooling
            "avoid_from": h["fan_helps_below"], "key": "fan.limit.healthy"}


def fan_state(temp_c: float, group: str) -> str:
    lim = fan_limits(group)
    if temp_c >= lim["avoid_from"]:
        return "avoid_fan_alone"
    if temp_c >= lim["not_enough_from"]:
        return "fan_not_enough_alone"
    return "fan_helps"


def fan_advice(indoor_hours: list, vulnerable: list) -> dict:
    # infants / pregnant / chronic illness: no fan-specific verified limit -> precautionary use of the stricter older-adult limit
    group = "older" if vulnerable else "adult"
    states = [{"time": h["time"], "state": fan_state(h["indoor"], group), "indoor": h["indoor"]} for h in indoor_hours]
    worst = max(states, key=lambda s: ["fan_helps", "fan_not_enough_alone", "avoid_fan_alone"].index(s["state"])) if states else None
    lim = fan_limits(group)
    return {"group": group, "precautionary": bool(vulnerable and not any(v == "elderly" for v in vulnerable)),
            "now": states[0]["state"] if states else None, "worst_next24": worst,
            "hours_avoid": [s["time"][11:16] for s in states if s["state"] == "avoid_fan_alone"],
            "hours_not_enough": [s["time"][11:16] for s in states if s["state"] == "fan_not_enough_alone"],
            "limits_c": {"not_enough_from": lim["not_enough_from"], "avoid_from": lim["avoid_from"]},
            "sources": [V.source(lim["key"]), V.source("fan.hot_dry_harm")]}
