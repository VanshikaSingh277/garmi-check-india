"""District daily normal maximum temperature (1991-2020, IMD gridded data) and the IMD station type of a point
(plains / hill / coastal), for IMD's departure-from-normal heatwave rule. Built by pipelines/india/district_normals.py."""
import json
import math
import os
from datetime import date
from functools import lru_cache

from . import verified as V

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


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


def normal_tmax(district_id: str, day: date, elev_m: float = None):
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


def station_type(lat: float, lon: float, elev_m: float = None) -> str:
    """IMD applies different heatwave rules to plains, hill and coastal stations but publishes no operational
    definition; the limits here are a labelled design choice (verified_numbers heat.station_type)."""
    st = V.value("heat.station_type")
    if elev_m is not None and elev_m >= st["hill_min_elev_m"]:
        return "hill"
    if coast_km(lat, lon) <= st["coastal_max_km"]:
        return "coastal"
    return "plains"
