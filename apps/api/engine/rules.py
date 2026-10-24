"""Heat level + fan advice. Every threshold is read from verified_numbers (see engine/verified.py).
Levels: 0 Low, 1 Moderate, 2 High, 3 Extreme, from the weather only; each step carries a reason code so the UI can explain it.
Household factors are listed beside the level (home_factors), not added to it."""
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


def risk(next24: list, today: list, tomorrow: list, in_delhi: bool = False, days: list = None, station: str = "plains") -> dict:
    """Today's heat level from the weather and official rules only (no household factors, no model output):
    - IMD heat-index bands, banded on the air temperature instead when it is higher (dry heat: the heat index reads
      below the air there, design choice) - verified_numbers heat_index.bands.imd / heat.band_on_air
    - IMD heatwave: actual Tmax >= 45 (severe >= 47), or Tmax above the station's entry value (plains 40, hills 30) and
      4.5-6.4 C above the 1991-2020 normal (severe above 6.4); coastal: Tmax >= 37 and >= 4.5 above normal.
      Severe heatwave -> Extreme, heatwave -> at least High
    - Delhi only: the Delhi HAP two-day 97th-percentile rule; everywhere: the wet-bulb danger limit -> Extreme
    days: [{"day": "today"|"tomorrow", "tmax": C, "normal": C or None, "uncertain": bool}] for the days whose afternoon
      is in next24; with an uncertain normal (raised ground, heat.normal_point) the departure rule stops at High;
    station: "plains" | "hill" | "coastal" (engine/normals.station_type)."""
    reasons = []
    hi_max = max(r["hi"] for r in next24)
    twb_max = max(r["twb"] for r in next24)
    tmax = max(r["t"] for r in next24)
    lvl = base_from_heat_index(max(hi_max, tmax))
    reasons.append({"code": "base_heat_index", "value": round(hi_max, 1), "source": V.source("heat_index.bands.imd")})
    if base_from_heat_index(tmax) > base_from_heat_index(hi_max):
        reasons.append({"code": "base_air_temp", "value": round(tmax, 1), "source": V.source("heat.band_on_air")})
    hw = V.value("imd.heatwave")
    entry = {"plains": hw["plains_min_tmax"], "hill": hw["hills_min_tmax"], "coastal": hw["coastal_min_tmax"]}[station]
    for d in days if days is not None else [{"day": None, "tmax": tmax, "normal": None}]:
        t, dep = d["tmax"], (round(d["tmax"] - d["normal"], 1) if d.get("normal") is not None else None)
        code = None
        if t >= hw["shw_actual_tmax"]:
            code = "severe_heatwave_tmax"
        elif dep is not None and t >= entry:
            if station == "coastal":
                code = "heatwave_coastal" if dep >= hw["coastal_hw_departure"] else None
            elif dep > hw["shw_departure_above"] and not d.get("uncertain"):
                code = "severe_heatwave_departure"
            elif dep > hw["shw_departure_above"]:            # less certain normal (raised ground): at most one level
                code = "heatwave_departure"
            elif dep >= hw["hw_departure"][0]:
                code = "heatwave_departure"
        if code is None and t >= hw["hw_actual_tmax"]:
            code = "heatwave_tmax"
        if code:
            lvl = 3 if code.startswith("severe") else max(lvl, 2)
            reasons.append({"code": code, "value": round(t, 1), "departure": dep, "normal": d.get("normal"), "day": d["day"],
                            "source": V.source("imd.heatwave")})
    p97 = V.value("delhi.heatwave.p97_daily_mean")["p97"]
    means = [sum(r["t"] for r in d) / len(d) for d in (today, tomorrow) if d]
    if in_delhi and len(means) == 2 and all(m > p97 for m in means) and lvl < 2:
        lvl = 2
        reasons.append({"code": "heatwave_p97", "value": [round(m, 1) for m in means], "threshold": p97, "source": V.source("delhi.heatwave.p97_daily_mean")})
    wb = V.value("wet_bulb.danger")
    if twb_max >= wb["critical_humid_young_mean"]:
        lvl = 3
        reasons.append({"code": "wet_bulb_critical", "value": round(twb_max, 1), "source": V.source("wet_bulb.danger")})
    return {"level": LEVELS[lvl], "level_index": lvl, "reasons": reasons, "hi_max": round(hi_max, 1), "twb_max": round(twb_max, 1),
            "tmax": round(tmax, 1), "station": station}


def home_factors(roof: str, care: list, devices: dict) -> list:
    """What makes the heat more dangerous in this home. Listed next to the level, never added to it: no published
    source says how much each factor raises the risk."""
    out = []
    if roof == "tin_top":                 # asbestos roofs arrive here as tin_top (same sheet-roof behaviour)
        out.append("tin_roof_top_floor")
    if care:
        out.append("vulnerable_person")
    if not (devices.get("fan") or devices.get("cooler") or devices.get("ac")):
        out.append("no_cooling")
    return out


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
