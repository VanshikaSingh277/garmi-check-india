"""District daily normal maximum temperature (1991-2020, IMD gridded data) and the IMD station type of a point
(plains / hill / coastal), for IMD's departure-from-normal heatwave rule. Built by pipelines/india/district_normals.py."""
import json
import math
import os
import threading
from datetime import date
from functools import lru_cache
from statistics import mean

import httpx

from . import verified as V

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
# runtime cache: outside the read-only data/ folder (spec §8.9), on the writable state volume
CACHE = os.path.join(os.environ.get("THANDAK_STATE_DIR", os.path.join(os.path.dirname(__file__), "..", ".cache")), "point_normals.json")
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
MAY = range((date(2001, 5, 1) - date(2001, 1, 1)).days, (date(2001, 5, 31) - date(2001, 1, 1)).days + 1)
_lock = threading.Lock()


@lru_cache(maxsize=1)
def _normals():
    p = os.path.join(DATA, "district_normals.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


@lru_cache(maxsize=1)
def _coast():
    p = os.path.join(DATA, "india_coastline.json")
    if not os.path.exists(p):
        return None
    from shapely.geometry import MultiLineString
    return MultiLineString(json.load(open(p, encoding="utf-8"))["lines"])


def available() -> bool:
    return _normals() is not None


def normal_tmax(district_id: str, day: date, elev_m: float | None = None):
    """Normal maximum temperature for that calendar day in the district, moved to the point's height when known."""
    n = _normals()
    d = n and n["districts"].get(district_id)
    if not d:
        return None
    doy = (date(2001, day.month, 28 if (day.month, day.day) == (2, 29) else day.day) - date(2001, 1, 1)).days
    v = d["tmax"][doy] / 10
    if elev_m is not None and d.get("elev_m") is not None:
        v += n["lapse_c_per_m"] * (elev_m - d["elev_m"])
    return round(v, 1)


def _load_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _era5_may_mean(lat, lon, elev_m):
    """ERA5 May mean daily maximum (2016-2020) at the point, downscaled to its height; None if the archive fails."""
    vals = []
    try:
        for y in range(2016, 2021):
            r = httpx.get(ARCHIVE, timeout=5.0, params={"latitude": lat, "longitude": lon, "elevation": elev_m, "daily": "temperature_2m_max",
                                                         "start_date": f"{y}-05-01", "end_date": f"{y}-05-31", "timezone": "Asia/Kolkata"})
            r.raise_for_status()
            vals += [x for x in r.json()["daily"]["temperature_2m_max"] if x is not None]
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    return round(mean(vals), 1) if len(vals) >= 100 else None


def point_normal_tmax(district_id: str, day: date, lat: float, lon: float, elev_m: float | None = None):
    """(normal, uncertain). On raised ground the district value can't stand for a hill town and the plains below it,
    so from heat.normal_point.min_elev_m up the district's seasonal curve is shifted to ERA5's May mean at the point
    itself (fetched once per ~5 km cell, then cached on disk). Normals there are less certain (uncertain=True)."""
    n = _normals()
    d = n and n["districts"].get(district_id)
    if not d:
        return None, True
    cfg = V.value("heat.normal_point")
    if elev_m is None or elev_m < cfg["min_elev_m"]:
        return normal_tmax(district_id, day, elev_m), False
    key = f"{round(lat * 20) / 20:.2f},{round(lon * 20) / 20:.2f}"
    with _lock:
        cache = _load_cache()
        may = cache.get(key)
        if may is None:
            may = _era5_may_mean(lat, lon, round(elev_m))
            if may is None:                                   # archive down: district value, still flagged uncertain
                return normal_tmax(district_id, day, elev_m), True
            cache[key] = may
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    doy = (date(2001, day.month, 28 if (day.month, day.day) == (2, 29) else day.day) - date(2001, 1, 1)).days
    shape = d["tmax"][doy] / 10 - mean(d["tmax"][i] for i in MAY) / 10
    return round(may + shape, 1), True


def coast_km(lat: float, lon: float) -> float:
    """Great-circle distance to the sea coast (inf when no coastline data or far north of it)."""
    c = _coast()
    if c is None:
        return math.inf
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    q = nearest_points(Point(lon, lat), c)[1]
    p1, p2, dl = math.radians(lat), math.radians(q.y), math.radians(q.x - lon)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def station_type(lat: float, lon: float, elev_m: float | None = None) -> str:
    """IMD applies different heatwave rules to plains, hill and coastal stations but publishes no operational
    definition; the limits here are a labelled design choice (verified_numbers heat.station_type)."""
    st = V.value("heat.station_type")
    if elev_m is not None and elev_m >= st["hill_min_elev_m"]:
        return "hill"
    if coast_km(lat, lon) <= st["coastal_max_km"]:
        return "coastal"
    return "plains"
