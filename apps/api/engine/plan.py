"""Hour-by-hour home plan built from the live forecast and the indoor model.

No new thresholds are introduced:
  - windows: OPEN when the forecast outdoor air is below the LOW end of the model's 80 % range for the room (outside is
    cooler even allowing for model error), CLOSE (and draw curtains) when it is above the HIGH end, otherwise either;
  - fan: the verified fan limits (rules.fan_limits) applied to the room estimate (or to outdoor air when the indoor
    model is not applicable - then no window advice is given);
  - hottest hours: the 3 warmest hours of the room estimate (or of the outdoor heat index)."""


def _ranges(hours, key, value):
    """[[start 'HH:MM', end 'HH:MM'], ...] for consecutive hours where hours[i][key] == value (end = last hour + 1 h)."""
    out, start = [], None
    for i, h in enumerate(hours):
        hit = h.get(key) == value
        if hit and start is None:
            start = i
        if start is not None and (not hit or i == len(hours) - 1):
            last = i if hit else i - 1
            end_h = (int(hours[last]["time"][11:13]) + 1) % 24
            out.append([hours[start]["time"][11:16], f"{end_h:02d}:00"])
            start = None
    return out


def build(indoor_hours: list, outdoor_hours: list, fan_limits: dict) -> dict:
    by_time = {h["time"]: h for h in indoor_hours}
    rows = []
    for o in outdoor_hours:
        i = by_time.get(o["time"])
        temp = i["indoor"] if i else o["t"]
        window = None
        if i:
            window = "open" if o["t"] < i["low"] else "close" if o["t"] > i["high"] else "either"
        fan = "avoid_fan_alone" if temp >= fan_limits["avoid_from"] else "fan_not_enough_alone" if temp >= fan_limits["not_enough_from"] else "fan_helps"
        rows.append({"time": o["time"], "outdoor": o["t"], "hi": o.get("hi"), "indoor": i["indoor"] if i else None,
                     "low": i["low"] if i else None, "high": i["high"] if i else None, "window": window, "fan": fan})
    key = (lambda r: r["indoor"]) if indoor_hours else (lambda r: r["hi"] if r["hi"] is not None else r["outdoor"])
    hottest = sorted(sorted(rows, key=key, reverse=True)[:3], key=lambda r: r["time"])
    return {"basis": "indoor" if indoor_hours else "outdoor", "hours": rows,
            "open": _ranges(rows, "window", "open"), "close": _ranges(rows, "window", "close"),
            "fan_not_enough": _ranges(rows, "fan", "fan_not_enough_alone"), "fan_avoid": _ranges(rows, "fan", "avoid_fan_alone"),
            "hottest": [r["time"][11:16] for r in hottest]}
