"""Phase 2 - weather history for Delhi.

Pulls hourly ERA5-Land (via Open-Meteo archive API, free for non-commercial use, attribution required)
on a 0.1-degree grid inside the Delhi boundary, 2021-01-01 .. END, plus daily mean temperature 2008-2019
at Safdarjung for the de Bont (2024) 97th-percentile heatwave definition.

Usage: python fetch_history.py <pylib_dir> <delhi_boundary.geojson> <raw_out_dir> <END yyyy-mm-dd>
Raw output stays outside the repo (blueprint rule: never raw data in the repo).
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, sys.argv[1])
import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
from shapely.geometry import Point  # noqa: E402

BOUNDARY, OUT, END = sys.argv[2], sys.argv[3], sys.argv[4]
os.makedirs(OUT, exist_ok=True)
API = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation"

poly = gpd.read_file(BOUNDARY).to_crs(4326).geometry.union_all()
minx, miny, maxx, maxy = poly.bounds
pts = [(round(la, 2), round(lo, 2))
       for la in np.arange(np.floor(miny * 10) / 10, maxy + 0.1, 0.1)
       for lo in np.arange(np.floor(minx * 10) / 10, maxx + 0.1, 0.1)
       if poly.buffer(0.03).contains(Point(lo, la))]
print("grid points inside Delhi:", len(pts))
json.dump(pts, open(os.path.join(OUT, "grid_points.json"), "w"))


def get(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:  # network / rate limit -> back off
            print("  retry", k + 1, e)
            time.sleep(10 * (k + 1))
    raise RuntimeError(url)


for la, lo in pts:
    fn = os.path.join(OUT, f"hourly_{la}_{lo}.json")
    if os.path.exists(fn):
        continue
    url = (f"{API}?latitude={la}&longitude={lo}&start_date=2021-01-01&end_date={END}"
           f"&hourly={HOURLY}&models=era5_land&timezone=Asia%2FKolkata")
    json.dump(get(url), open(fn, "w"))
    print("saved", fn)
    time.sleep(1.5)

fn = os.path.join(OUT, "daily_safdarjung_2008_2019.json")
if not os.path.exists(fn):
    url = (f"{API}?latitude=28.58&longitude=77.21&start_date=2008-01-01&end_date=2019-12-31"
           f"&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min&models=era5_land&timezone=Asia%2FKolkata")
    json.dump(get(url), open(fn, "w"))
    print("saved", fn)
