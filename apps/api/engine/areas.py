"""Ward lookup (point-in-polygon) and area summaries from precomputed layers (data/wards.geojson)."""
import json
import os
from functools import lru_cache

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "wards.geojson")


@lru_cache(maxsize=1)
def _index():
    gj = json.load(open(PATH, encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in gj["features"]]
    props = [f["properties"] for f in gj["features"]]
    for p in props:
        if isinstance(p.get("drivers"), str):
            p["drivers"] = json.loads(p["drivers"])
    return STRtree(geoms), geoms, props


def ward_at(lat: float, lon: float):
    tree, geoms, props = _index()
    pt = Point(lon, lat)
    for i in tree.query(pt):
        if geoms[i].contains(pt):
            return props[i]
    # nearest within ~1 km if the point falls just outside (boundary simplification)
    i = tree.nearest(pt)
    return props[i] if geoms[i].distance(pt) < 0.01 else None


def city_stats():
    _, _, props = _index()
    vals = sorted(p["lst_day_mean_c"] for p in props if p.get("lst_day_mean_c") is not None)
    return {"lst_day_median": vals[len(vals) // 2], "n_wards": len(props)}


def percentile(field: str, value: float) -> float:
    _, _, props = _index()
    vals = [p[field] for p in props if p.get(field) is not None]
    return round(sum(v <= value for v in vals) / len(vals), 2)
