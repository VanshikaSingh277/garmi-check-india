"""Surface temperature (Landsat LST) against measured air temperature at IMD stations, pass by pass.

For every clear Landsat 8/9 pass over a station (Apr-Jun 2021-2025), LST is averaged over 1 km around the station (station
coordinates are published to about 1 km) and paired with the station's air temperature at the time of the pass, linearly
interpolated between the hourly reports. Air temperature: IMD synoptic stations via Meteostat bulk hourly data
(https://dev.meteostat.net, CC BY-NC 4.0). LST: same scaling and cloud mask as pipelines/satellite/landsat_lst_composite.py.

What this answers: how far the satellite's surface temperature sits above the air people breathe at the same moment, how
well the two move together, and whether hotter-surface places are also hotter-air places. Six stations is a sanity check,
not a full validation; CPCB/IMD station networks would make it one (docs/TEAM_TODO.md).
Usage (repo root):  .venv/Scripts/python.exe -X utf8 ml/validation/lst_vs_air.py
Writes ml/validation/lst_vs_air.json (summary) and ml/validation/lst_vs_air_pairs.csv (every pair)."""
import gzip
import io
import json
import os
from datetime import datetime, timezone

import httpx
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

R = os.path.join(os.path.dirname(__file__), "..", "..")
OUT = os.path.dirname(__file__)
CACHE = os.path.join(R, "data", "cache", "meteostat")
STATIONS = [  # Meteostat id, city, name, lat, lon (from Meteostat's station list)
    ("42182", "Delhi", "Safdarjung", 28.5833, 77.2000),
    ("42181", "Delhi", "Palam", 28.5667, 77.1167),
    ("42647", "Ahmedabad", "Ahmedabad", 23.0667, 72.6333),
    ("43128", "Hyderabad", "Hyderabad Airport (Begumpet)", 17.4500, 78.4667),
    ("VOHS0", "Hyderabad", "Hyderabad (Shamshabad)", 17.2406, 78.4289),
    ("42348", "Jaipur", "Jaipur Sanganer", 26.8167, 75.8000),
]
COLS = ["date", "hour", "temp", "dwpt", "rhum", "prcp", "snow", "wdir", "wspd", "wpgt", "pres", "tsun", "coco"]
BAD = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | 1
HALF = 500.0  # metres around the station


def hourly(sid):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{sid}.csv.gz")
    if not os.path.exists(path):
        r = httpx.get(f"https://bulk.meteostat.net/v2/hourly/{sid}.csv.gz", timeout=120, follow_redirects=True)
        r.raise_for_status()
        open(path, "wb").write(r.content)
    d = pd.read_csv(io.BytesIO(gzip.open(path).read()), names=COLS)
    d["t"] = pd.to_datetime(d["date"]) + pd.to_timedelta(d["hour"], unit="h")
    return d.dropna(subset=["temp"]).set_index("t")["temp"].sort_index()


def air_at(series, when):
    w = pd.Timestamp(when).tz_convert(None)
    before, after = series[:w].tail(1), series[w:].head(1)
    if before.empty or after.empty:
        return None
    t0, t1 = before.index[0], after.index[0]
    if (t1 - t0) > pd.Timedelta(hours=3):
        return None
    if t1 == t0:
        return float(before.iloc[0])
    f = (w - t0) / (t1 - t0)
    return float(before.iloc[0] + f * (after.iloc[0] - before.iloc[0]))


cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
pairs = []
for sid, city, name, lat, lon in STATIONS:
    air = hourly(sid)
    items = [i for i in cat.search(collections=["landsat-c2-l2"], intersects={"type": "Point", "coordinates": [lon, lat]},
                                   datetime="2021-04-01/2025-06-30",
                                   query={"eo:cloud_cover": {"lt": 40}, "platform": {"in": ["landsat-8", "landsat-9"]}}).items()
             if i.datetime.month in (4, 5, 6)]
    n = 0
    for it in items:
        try:
            with rasterio.open(it.assets["lwir11"].href) as st_src, rasterio.open(it.assets["qa_pixel"].href) as qa_src:
                x, y = Transformer.from_crs(4326, st_src.crs, always_xy=True).transform(lon, lat)
                win = from_bounds(x - HALF, y - HALF, x + HALF, y + HALF, st_src.transform)
                st = st_src.read(1, window=win).astype("float32")
                qa = qa_src.read(1, window=win)
        except Exception as e:
            print("skip", it.id, str(e)[:60])
            continue
        lst = st * 0.00341802 + 149.0 - 273.15
        ok = (st > 0) & ((qa & BAD) == 0) & (lst > 5) & (lst < 75)
        if ok.mean() < 0.8:
            continue
        when = it.datetime if it.datetime.tzinfo else it.datetime.replace(tzinfo=timezone.utc)
        ta = air_at(air, when)
        if ta is None:
            continue
        pairs.append({"station": sid, "city": city, "name": name, "time_utc": when.strftime("%Y-%m-%dT%H:%M"),
                      "lst_c": round(float(lst[ok].mean()), 2), "air_c": round(ta, 2)})
        n += 1
    print(city, name, "pairs", n, flush=True)

p = pd.DataFrame(pairs)
p["diff_c"] = p.lst_c - p.air_c
p.to_csv(os.path.join(OUT, "lst_vs_air_pairs.csv"), index=False)
per = []
for (sid, city, name), g in p.groupby(["station", "city", "name"]):
    per.append({"station": sid, "city": city, "name": name, "pairs": len(g),
                "lst_median_c": round(float(g.lst_c.median()), 1), "air_median_c": round(float(g.air_c.median()), 1),
                "lst_minus_air_median_c": round(float(g.diff_c.median()), 1),
                "lst_minus_air_p10_p90_c": [round(float(v), 1) for v in np.percentile(g.diff_c, [10, 90])],
                "pass_to_pass_r": round(float(np.corrcoef(g.lst_c, g.air_c)[0, 1]), 2) if len(g) > 4 else None})
st = pd.DataFrame(per)
fit = np.polyfit(p.air_c, p.lst_c, 1)
summary = {
    "about": "Landsat surface temperature vs IMD station air temperature at the moment of each clear pass (ml/validation/lst_vs_air.py).",
    "built": datetime.now(timezone.utc).date().isoformat(),
    "air_source": "IMD synoptic stations via Meteostat bulk hourly (CC BY-NC 4.0)",
    "lst_source": "Landsat 8/9 Collection 2 Level-2 ST_B10, 1 km mean around each station, Apr-Jun 2021-2025",
    "pairs": len(p), "stations": per,
    "all_pairs": {"lst_minus_air_median_c": round(float(p.diff_c.median()), 1),
                  "lst_minus_air_p10_p90_c": [round(float(v), 1) for v in np.percentile(p.diff_c, [10, 90])],
                  "r": round(float(np.corrcoef(p.lst_c, p.air_c)[0, 1]), 2),
                  "lst_per_air_c_slope": round(float(fit[0]), 2)},
    "between_stations": {"spearman_lst_vs_air_medians": round(float(st.lst_median_c.rank().corr(st.air_median_c.rank())), 2),
                         "n": len(st)},
    "reading": "Surface temperature runs well above air temperature at the late-morning pass, so LST maps show where surfaces "
               "heat most, not the air temperature people feel. Use LST to rank and compare places, and forecasts or station "
               "air temperature for health thresholds.",
}
with open(os.path.join(OUT, "lst_vs_air.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(summary, f, indent=1)
print(json.dumps({k: summary[k] for k in ("pairs", "all_pairs", "between_stations")}, indent=1))
for s in per:
    print(s)
