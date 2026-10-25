"""Heat level per calendar day for a place (the jobs and the WhatsApp bot), with the same weather-only rules as
/api/status/individual: IMD bands on max(air, heat index), IMD heatwave rules with the day's normal, wet-bulb limit."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from engine import normals, rules, weather

IST = ZoneInfo("Asia/Kolkata")


def day_rows(w: dict, day: str) -> list:
    return [r for r in w["hourly"] if r["time"][:10] == day]


def day_level(w: dict, day: str, lat: float, lon: float, district_id: str | None, in_delhi: bool, label: str,
              imd_color: str | None = None) -> dict | None:
    rows = day_rows(w, day)
    if not rows:
        return None
    tmax = w.get("daily_tmax", {}).get(day, max(r["t"] for r in rows))
    normal = normals.point_normal_tmax(district_id, date.fromisoformat(day), lat, lon, w.get("elevation"))[0] if district_id else None
    station = normals.station_type(lat, lon, w.get("elevation"))
    today = day_rows(w, datetime.now(IST).date().isoformat())
    r = rules.risk(rows, today, rows, in_delhi=in_delhi, days=[{"day": label, "tmax": round(tmax, 1), "normal": normal}], station=station,
                   imd_color=imd_color)
    return {"date": day, "level": r["level"], "level_index": r["level_index"], "reasons": [x["code"] for x in r["reasons"]]}


def today_and_tomorrow(lat: float, lon: float, district_id: str | None, in_delhi: bool) -> dict:
    w = weather.fetch(lat, lon)
    today = datetime.now(IST).date()
    days = sorted({r["time"][:10] for r in w["hourly"] if r["time"][:10] >= today.isoformat()})
    out = {"weather": w, "today": None, "tomorrow": None}
    if days:
        out["today"] = day_level(w, days[0], lat, lon, district_id, in_delhi, "today")
    if len(days) > 1:
        out["tomorrow"] = day_level(w, days[1], lat, lon, district_id, in_delhi, "tomorrow")
    return out


def window_level(w: dict, day: str, start: str, end: str) -> int:
    """Heat-index band (on max(air, heat index)) during a work window, e.g. 09:00-17:00 today."""
    rows = [r for r in day_rows(w, day) if start <= r["time"][11:16] < end]
    if not rows:
        return 0
    return rules.base_from_heat_index(max(max(r["hi"], r["t"]) for r in rows))
