"""Second step after district_normals.py: anchor the normals of raised districts (point >= 600 m) to ERA5.

Why: IMD's 1 deg grid is interpolated from stations, and in the hills those stations sit lower (warmer) than the towns,
so a lapse correction from the cell's mean ground height isn't enough. Shimla came out 31.1 C in May against IMD's
station normal of about 24.5 C, which would hide hill heatwaves. ERA5 (Open-Meteo archive, downscaled to the point's
height) matched Shimla within 0.5 C, so for these districts the IMD seasonal curve is kept and shifted so that its
May mean equals ERA5's May mean for 2016-2020 (5 Mays per district keeps the free API cost to ~11 calls each).

Usage: python -I district_normals_hills.py <data_dir>
Updates <data_dir>/district_normals.json (per district: era5_offset_c) and district_normals_checks.json.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import date
from statistics import mean

OUT = sys.argv[1]
MIN_ELEV = 600
YEARS = range(2016, 2021)
API = "https://archive-api.open-meteo.com/v1/archive"
BATCH = 20
MAY = range((date(2001, 5, 1) - date(2001, 1, 1)).days, (date(2001, 5, 31) - date(2001, 1, 1)).days + 1)

path = os.path.join(OUT, "district_normals.json")
n = json.load(open(path, encoding="utf-8"))
hills = [(k, v) for k, v in n["districts"].items() if v["elev_m"] >= MIN_ELEV]


def get(url):
    for attempt in range(8):
        try:
            return json.load(urllib.request.urlopen(url, timeout=120))
        except Exception as e:          # mostly 429: back off
            print("retry", attempt + 1, repr(e)[:100], file=sys.stderr)
            time.sleep(20 * (attempt + 1))
    raise SystemExit("archive API failed")


era5 = {k: [] for k, _ in hills}
for s in range(0, len(hills), BATCH):
    chunk = hills[s:s + BATCH]
    q = (f"latitude={','.join(str(v['lat']) for _, v in chunk)}&longitude={','.join(str(v['lon']) for _, v in chunk)}"
         f"&elevation={','.join(str(v['elev_m']) for _, v in chunk)}&daily=temperature_2m_max&timezone=Asia%2FKolkata")
    for y in YEARS:
        d = get(f"{API}?{q}&start_date={y}-05-01&end_date={y}-05-31")
        d = d if isinstance(d, list) else [d]
        for (k, _), r in zip(chunk, d):
            era5[k] += [x for x in r["daily"]["temperature_2m_max"] if x is not None]
        time.sleep(2)
    print(f"{min(s + BATCH, len(hills))}/{len(hills)}", file=sys.stderr)

offsets = []
for k, v in hills:
    imd_may = mean(v["tmax"][i] for i in MAY) / 10
    off = round(mean(era5[k]) - imd_may, 1)
    v["tmax"] = [int(round(x + off * 10)) for x in v["tmax"]]
    v["era5_offset_c"] = off
    offsets.append((off, v["district"], v["state"], v["elev_m"]))
n["method"] += f"; districts at >= {MIN_ELEV} m shifted so their May mean equals ERA5 May 2016-2020 (era5_offset_c)"
json.dump(n, open(path, "w", encoding="utf-8"), separators=(",", ":"))

# re-check against the reference stations with the stored district values (district point -> station height by lapse)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))
from engine import districts  # noqa: E402
chk_path = os.path.join(OUT, "district_normals_checks.json")
chk = json.load(open(chk_path, encoding="utf-8"))
REF = {"New Delhi (Safdarjung)": (28.58, 77.21), "Jaipur": (26.82, 75.80), "Chennai": (13.00, 80.18), "Nagpur": (21.10, 79.05),
       "Shimla": (31.10, 77.17), "Ahmedabad": (23.07, 72.63)}
for c in chk["may_checks"]:
    lat, lon = REF[c["place"]]
    dd = n["districts"][districts.district_at(lat, lon)["id"]]
    v = mean(dd["tmax"][i] for i in MAY) / 10 + n["lapse_c_per_m"] * (c["elev_m"] - dd["elev_m"])
    c["may_normal_c"], c["diff_c"] = round(v, 1), round(v - c["imd_station_approx_c"], 1)
offsets.sort()
chk["hill_anchor"] = {"min_elev_m": MIN_ELEV, "n_districts": len(hills), "years": "2016-2020 (May)",
                      "offset_c_min_median_max": [offsets[0][0], offsets[len(offsets) // 2][0], offsets[-1][0]],
                      "largest": [{"district": o[1], "state": o[2], "elev_m": o[3], "offset_c": o[0]} for o in offsets[:5]]}
json.dump(chk, open(chk_path, "w", encoding="utf-8"), indent=1)
print(json.dumps({"checks": chk["may_checks"], "hill_anchor": chk["hill_anchor"]}, indent=1))
