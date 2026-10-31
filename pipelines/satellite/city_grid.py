"""One 90 m grid per city with pre-monsoon surface temperature and the land-surface features Model A uses.
Same sources and formulas as landsat_lst_composite.py, landsat_sr_indices.py and modis_night_and_worldcover.py, but read
straight onto a 90 m grid (about the Landsat thermal band's native 100 m) for any city, so other cities get the same
hotspot detail as Delhi. All sources are free on Microsoft Planetary Computer (no account):
- Landsat 8/9 Collection 2 Level-2 (USGS, public domain): LST from ST_B10 ("lwir11"), K = DN * 0.00341802 + 149.0;
  QA_PIXEL fill, dilated cloud, cirrus, cloud and shadow masked; Apr-Jun 2021-2026, per-year median then median of years.
  Reflectance (DN * 0.0000275 - 0.2), Apr-Jun 2025-2026 median: NDVI, NDBI, MNDWI, Liang (2001) albedo.
- ESA WorldCover 2021 v200 (CC BY 4.0): class shares per cell from the 10 m map.
- Copernicus DEM GLO-30: mean elevation per cell.
Surface temperature is the ~10:30 overpass skin temperature, not air temperature.

Usage (repo root):  .venv/Scripts/python.exe -X utf8 pipelines/satellite/city_grid.py <city>
Output: data/cache/cities/<city>.npz (not in git; rebuild with this script)."""
import json
import os
import sys
import time

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from scipy.ndimage import distance_transform_edt

R = os.path.join(os.path.dirname(__file__), "..", "..")
OUT = os.path.join(R, "data", "cache", "cities")
RES = 90.0
# Study boxes: Delhi uses the extent of its wards; other cities a box around the city centre covering the urban area.
CITIES = {
    "delhi": {"name": "Delhi", "wards": True},
    "ahmedabad": {"name": "Ahmedabad", "center": (72.5714, 23.0225), "half_km": 16},
    "hyderabad": {"name": "Hyderabad", "center": (78.4867, 17.3850), "half_km": 20},
    "jaipur": {"name": "Jaipur", "center": (75.7873, 26.9124), "half_km": 15},
}
WC = {"tree": [10], "lowveg": [20, 30], "crop": [40], "built": [50], "bare": [60], "water": [80, 90]}
BAD = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | 1
SR = ["blue", "green", "red", "nir08", "swir16", "swir22"]


def grid(city):
    c = CITIES[city]
    if c.get("wards"):
        with open(os.path.join(R, "apps", "api", "data", "wards.geojson"), encoding="utf-8") as f:
            pts = [p for ft in json.load(f)["features"] for ring in _rings(ft["geometry"]) for p in ring]
        lon0 = sum(p[0] for p in pts) / len(pts)
        box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    else:
        lon0 = c["center"][0]
        box = None
    crs = f"EPSG:{32600 + int((lon0 + 180) // 6) + 1}"
    to = Transformer.from_crs(4326, crs, always_xy=True)
    if box:
        xs, ys = to.transform([box[0], box[2], box[0], box[2]], [box[1], box[1], box[3], box[3]])
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    else:
        cx, cy = to.transform(*c["center"])
        h = c["half_km"] * 1000
        minx, maxx, miny, maxy = cx - h, cx + h, cy - h, cy + h
    minx, miny = np.floor(minx / RES) * RES, np.floor(miny / RES) * RES
    w, hgt = int(np.ceil((maxx - minx) / RES)), int(np.ceil((maxy - miny) / RES))
    tr = from_origin(minx, miny + hgt * RES, RES, RES)
    back = Transformer.from_crs(crs, 4326, always_xy=True)
    bbox = back.transform([minx, minx + w * RES], [miny, miny + hgt * RES])
    return crs, tr, w, hgt, [min(bbox[0]), min(bbox[1]), max(bbox[0]), max(bbox[1])]


def _rings(g):
    if g["type"] == "Polygon":
        return g["coordinates"]
    return [r for poly in g["coordinates"] for r in poly]


def read(href, crs, tr, w, h, rs, dtype="float32"):
    for attempt in range(3):
        try:
            with rasterio.open(href) as s, WarpedVRT(s, crs=crs, transform=tr, width=w, height=h, resampling=rs) as v:
                return v.read(1).astype(dtype)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def main(city):
    os.makedirs(OUT, exist_ok=True)
    crs, tr, w, h, bbox = grid(city)
    print(city, "grid", w, "x", h, crs, flush=True)
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)

    def landsat(dates, cloud):
        return [i for i in cat.search(collections=["landsat-c2-l2"], bbox=bbox, datetime=dates,
                                      query={"eo:cloud_cover": {"lt": cloud}, "platform": {"in": ["landsat-8", "landsat-9"]}}).items()
                if i.datetime.month in (4, 5, 6)]

    yearly, used = {}, 0
    for it in sorted(landsat("2021-04-01/2026-06-30", 20), key=lambda x: x.datetime):
        try:
            st = read(it.assets["lwir11"].href, crs, tr, w, h, Resampling.average)
            qa = read(it.assets["qa_pixel"].href, crs, tr, w, h, Resampling.nearest, "uint16")
        except Exception as e:
            print("skip", it.id, str(e)[:60], flush=True)
            continue
        lst = st * 0.00341802 + 149.0 - 273.15
        lst[(st == 0) | ((qa & BAD) != 0) | (lst < 5) | (lst > 75)] = np.nan
        if np.isfinite(lst).mean() < 0.05:
            continue
        yearly.setdefault(it.datetime.year, []).append(lst)
        used += 1
    lst = np.nanmedian(np.stack([np.nanmedian(np.stack(a), axis=0) for a in yearly.values()]), axis=0)
    print(city, "LST scenes", used, "years", sorted(yearly), flush=True)

    stacks = {k: [] for k in SR}
    for it in landsat("2025-04-01/2026-06-30", 10):
        try:
            qa = read(it.assets["qa_pixel"].href, crs, tr, w, h, Resampling.nearest, "uint16")
            bad = (qa & BAD) != 0
            if (~bad & (qa > 0)).mean() < 0.3:
                continue
            for k in SR:
                a = read(it.assets[k].href, crs, tr, w, h, Resampling.average)
                r = a * 0.0000275 - 0.2
                r[bad | (a == 0)] = np.nan
                stacks[k].append(r)
        except Exception as e:
            print("skip", it.id, str(e)[:60], flush=True)
    med = {k: np.nanmedian(np.stack(v), axis=0) for k, v in stacks.items()}
    B, G, Rd, N, S1, S2 = (med[k] for k in SR)
    print(city, "SR scenes", len(stacks["red"]), flush=True)

    tr10 = rasterio.Affine(10, 0, tr.c, 0, -10, tr.f)
    wc = np.zeros((h * 9, w * 9), "uint8")
    for it in cat.search(collections=["esa-worldcover"], bbox=bbox).items():
        if "2021" not in str(it.datetime) and "v200" not in it.id:
            continue
        a = read(it.assets["map"].href, crs, tr10, w * 9, h * 9, Resampling.nearest, "uint8")
        wc = np.where(wc == 0, a, wc)
    frac = {k: np.isin(wc, v).reshape(h, 9, w, 9).mean(axis=(1, 3)).astype("float32") for k, v in WC.items()}

    dem = np.full((h, w), np.nan, "float32")
    for it in cat.search(collections=["cop-dem-glo-30"], bbox=bbox).items():
        a = read(it.assets["data"].href, crs, tr, w, h, Resampling.average)
        dem = np.where(np.isfinite(dem) | (a <= -1000), dem, a)
    dist_water = distance_transform_edt(frac["water"] < 0.5) * RES

    xs = tr.c + (np.arange(w) + 0.5) * RES
    ys = tr.f - (np.arange(h) + 0.5) * RES
    X, Y = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(X, Y)
    np.savez_compressed(os.path.join(OUT, f"{city}.npz"), lst=lst.astype("float32"),
                        ndvi=((N - Rd) / (N + Rd)).astype("float32"), ndbi=((S1 - N) / (S1 + N)).astype("float32"),
                        mndwi=((G - S1) / (G + S1)).astype("float32"),
                        albedo=(0.356 * B + 0.130 * Rd + 0.373 * N + 0.085 * S1 + 0.072 * S2 - 0.0018).astype("float32"),
                        elevation=dem, dist_water=dist_water.astype("float32"), lon=lon.astype("float32"), lat=lat.astype("float32"),
                        **{"f_" + k: v for k, v in frac.items()},
                        meta=json.dumps({"city": city, "name": CITIES[city]["name"], "crs": crs, "res_m": RES, "transform": list(tr)[:6],
                                         "lst_scenes": used, "lst_years": sorted(yearly), "sr_scenes": len(stacks["red"])}))
    v = lst[np.isfinite(lst)]
    print(city, "done: LST p5 %.1f p50 %.1f p95 %.1f" % tuple(np.percentile(v, [5, 50, 95])), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
