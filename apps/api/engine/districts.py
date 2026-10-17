"""All-India district heat layer (data/india_districts.geojson, built by pipelines/india/district_layer.py)."""
import bisect
import json
import os
from functools import lru_cache

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PATH = os.path.join(DATA, "india_districts.geojson")
PUBLIC = ["id", "district", "state", "lat", "lon", "area_km2", "pop_total", "pop_under5", "pop_65plus", "share_under5", "share_65plus",
          "density_per_km2", "tmax_mean_c", "tmin_mean_c", "twb_max_mean_c", "days_tmax_ge40", "tmax_p95_c", "hx_E", "hx_S",
          "hx_index", "hx_rank", "hx_class"]


def available() -> bool:
    return os.path.exists(PATH)


@lru_cache(maxsize=1)
def _index():
    gj = json.load(open(PATH, encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in gj["features"]]
    props = [f["properties"] for f in gj["features"]]
    valid = [p for p in props if not p.get("no_data") and p.get("hx_index") is not None]
    sorted_vals = {k: sorted(p[k] for p in valid if p.get(k) is not None)
                   for k in ["tmax_mean_c", "tmin_mean_c", "twb_max_mean_c", "days_tmax_ge40", "share_65plus", "share_under5",
                             "density_per_km2", "hx_index"]}
    return STRtree(geoms), geoms, props, valid, sorted_vals


def public(p: dict) -> dict:
    return {**{k: p.get(k) for k in PUBLIC}, "n_india": len(_index()[3])}


def district_at(lat: float, lon: float):
    """Polygon containing the point (None outside India or in the no-data area)."""
    if not available():
        return None
    tree, geoms, props, _, _ = _index()
    pt = Point(lon, lat)
    hit = next((props[i] for i in tree.query(pt) if geoms[i].contains(pt)), None)
    if hit is None:  # simplified coastlines: accept the nearest district within ~3 km
        i = tree.nearest(pt)
        hit = props[i] if geoms[i].distance(pt) < 0.03 else None
    return None if hit is None or hit.get("no_data") else hit


def percentile(field: str, value) -> float:
    """Share of Indian districts with a value <= this one (0..1)."""
    vals = _index()[4][field]
    return round(bisect.bisect_right(vals, value) / len(vals), 2) if value is not None and vals else None


def percentiles(p: dict) -> dict:
    return {k: percentile(k, p.get(k)) for k in ["tmax_mean_c", "tmin_mean_c", "twb_max_mean_c", "days_tmax_ge40", "share_65plus", "hx_index"]}


def ranking(state: str = None, limit: int = 100) -> dict:
    _, _, _, valid, _ = _index()
    rows = sorted((p for p in valid if not state or p.get("state") == state), key=lambda p: p["hx_rank"])
    return {"districts": [public(p) for p in rows[:limit]], "n": len(rows), "n_india": len(valid),
            "states": sorted({p["state"] for p in valid if p.get("state")})}


def checks() -> dict:
    path = os.path.join(DATA, "india_district_checks.json")
    return json.load(open(path)) if os.path.exists(path) else {}
