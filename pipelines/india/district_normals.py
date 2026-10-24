"""Daily normal maximum temperature (1991-2020) for every district, for IMD's departure-from-normal heatwave rule.

Inputs
  - IMD gridded daily maximum temperature, 1 deg x 1 deg, 1991-2020 (Srivastava et al. 2009, IMD Pune; one binary file
    per year from https://www.imdpune.gov.in/cmpg/Griddata/maxtemp.php, float32 [day, lat 7.5..37.5, lon 67.5..97.5],
    99.9 = no data). IMD itself uses 1991-2020 normals (IMD FAQ on heat wave).
  - Elevation: Open-Meteo elevation API (Copernicus DEM 90 m) at each district's representative point and on a
    0.25 deg sub-grid inside each 1 deg cell (the cell's mean ground height).
  - Natural Earth 50 m coastline (public domain), for the coastal-station rule.

Method
  normal(day) = mean over 1991-2020 of that calendar day (29 Feb folded into 28 Feb), smoothed with a centred 15-day mean.
  District value = bilinear blend of the 4 surrounding cell centres, each moved from its cell's mean height to the
  district point with a -6.5 degC/km lapse rate (otherwise a 1 deg cell smears hill towns with the plains below them).

Usage: python -I district_normals.py <grd_dir> <ne_50m_coastline.geojson> <data_dir>
Outputs: <data_dir>/district_normals.json, india_coastline.json, district_normals_checks.json
"""
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import date, timedelta

import numpy as np
from shapely.geometry import LineString, box, shape

GRD, COAST, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
YEARS = range(1991, 2021)
LAT0, LON0, N = 7.5, 67.5, 31
LAPSE = -6.5 / 1000          # degC per metre (standard environmental lapse rate; design choice)
SMOOTH = 15                  # days
ELEV_API = "https://api.open-meteo.com/v1/elevation"

# ---------- 30-year daily climatology per cell ----------
DOY = [(date(2001, 1, 1) + timedelta(days=i)) for i in range(365)]       # non-leap calendar
idx = {(d.month, d.day): i for i, d in enumerate(DOY)}
total, count = np.zeros((365, N, N)), np.zeros((365, N, N))
for y in YEARS:
    a = np.fromfile(os.path.join(GRD, f"tmax{y}.grd"), "<f4")
    days = a.size // (N * N)
    a = a.reshape(days, N, N).astype("float64")
    for k in range(days):
        d = date(y, 1, 1) + timedelta(days=k)
        i = idx.get((d.month, d.day), idx[(2, 28)])
        ok = a[k] < 99
        total[i][ok] += a[k][ok]
        count[i][ok] += 1
clim = np.where(count >= 25, total / np.maximum(count, 1), np.nan)    # at least 25 of 30 years
half = SMOOTH // 2
smooth = np.nanmean(np.stack([np.roll(clim, s, axis=0) for s in range(-half, half + 1)]), axis=0)
valid = ~np.isnan(smooth).any(axis=0)                                   # (lat, lon) cells with a full year


def elevations(points):
    out = []
    for s in range(0, len(points), 100):
        chunk = points[s:s + 100]
        url = f"{ELEV_API}?latitude={','.join(f'{p[0]:.4f}' for p in chunk)}&longitude={','.join(f'{p[1]:.4f}' for p in chunk)}"
        for attempt in range(8):
            try:
                out += json.load(urllib.request.urlopen(url, timeout=60))["elevation"]
                break
            except Exception as e:          # mostly 429 (rate limit): back off
                print("elevation retry", attempt + 1, repr(e)[:120], file=sys.stderr)
                time.sleep(15 * (attempt + 1))
        else:
            raise SystemExit("elevation API failed")
        time.sleep(1.5)
    return [max(0.0, e if e is not None and e == e else 0.0) for e in out]  # sea / no data -> 0 m


# ---------- mean ground height of each valid cell ----------
cells = [(i, j) for i in range(N) for j in range(N) if valid[i, j]]
offs = [-0.375, -0.125, 0.125, 0.375]
sub = [(LAT0 + i + a, LON0 + j + b) for i, j in cells for a in offs for b in offs]
sub_e = elevations(sub)
cell_elev = np.full((N, N), np.nan)
for n, (i, j) in enumerate(cells):
    cell_elev[i, j] = float(np.mean(sub_e[16 * n:16 * n + 16]))

# ---------- districts ----------
rows = list(csv.DictReader(open(os.path.join(OUT, "india_district_stats.csv"), encoding="utf-8")))
rows = [r for r in rows if r["no_data"] != "True" and r["lat"]]
pt_e = elevations([(float(r["lat"]), float(r["lon"])) for r in rows])


def at_point(lat, lon, elev):
    """365 daily normals at a point: bilinear over the 4 surrounding cell centres, lapse-corrected to `elev`."""
    fi, fj = lat - LAT0, lon - LON0
    i0, j0 = int(np.floor(fi)), int(np.floor(fj))
    acc, wsum = np.zeros(365), 0.0
    for di in (0, 1):
        for dj in (0, 1):
            i, j = i0 + di, j0 + dj
            if not (0 <= i < N and 0 <= j < N and valid[i, j]):
                continue
            w = (1 - abs(fi - i)) * (1 - abs(fj - j))
            if w <= 0:
                continue
            acc += w * (smooth[:, i, j] + LAPSE * (elev - cell_elev[i, j]))
            wsum += w
    if wsum == 0:                                                       # off the grid's land mask: nearest valid cell
        d2 = [((LAT0 + i - lat) ** 2 + (LON0 + j - lon) ** 2, i, j) for i, j in cells]
        _, i, j = min(d2)
        return smooth[:, i, j] + LAPSE * (elev - cell_elev[i, j]), "nearest"
    return acc / wsum, "bilinear"


out, how = {}, {"bilinear": 0, "nearest": 0}
for r, e in zip(rows, pt_e):
    v, m = at_point(float(r["lat"]), float(r["lon"]), e)
    how[m] += 1
    out[r["id"]] = {"district": r["district"], "state": r["state"], "lat": float(r["lat"]), "lon": float(r["lon"]),
                    "elev_m": round(e), "tmax": [int(round(x * 10)) for x in v]}

json.dump({"about": "Daily normal maximum temperature, 1991-2020, for IMD's departure-from-normal heatwave rule. "
                    "tmax[d] is tenths of degC for day d of a non-leap year (0 = 1 Jan; 29 Feb uses 28 Feb).",
           "source": "IMD gridded daily Tmax 1 deg (Srivastava et al. 2009, IMD Pune), 1991-2020; elevation Copernicus DEM via Open-Meteo",
           "method": f"30-year calendar-day mean, centred {SMOOTH}-day smoothing, bilinear from cell centres, lapse {LAPSE * 1000:g} degC/km from cell mean height",
           "baseline": "1991-2020", "lapse_c_per_m": LAPSE, "districts": out},
          open(os.path.join(OUT, "district_normals.json"), "w", encoding="utf-8"), separators=(",", ":"))

# ---------- coastline near India (for the coastal-station rule) ----------
clip = box(66.0, 5.0, 99.0, 25.5)
lines = []
for f in json.load(open(COAST, encoding="utf-8"))["features"]:
    g = shape(f["geometry"]).intersection(clip)
    for part in getattr(g, "geoms", [g]):
        if isinstance(part, LineString) and not part.is_empty:
            s = part.simplify(0.01)
            lines.append([[round(x, 3), round(y, 3)] for x, y in s.coords])
json.dump({"source": "Natural Earth 50 m coastline (public domain), clipped to 66-99E, 5-25.5N", "lines": lines},
          open(os.path.join(OUT, "india_coastline.json"), "w", encoding="utf-8"), separators=(",", ":"))

# ---------- checks against IMD station normals (approximate May mean maximum, IMD 1991-2020 climatology) ----------
REF = [("New Delhi (Safdarjung)", 28.58, 77.21, 39.5), ("Jaipur", 26.82, 75.80, 40.5), ("Chennai", 13.00, 80.18, 37.5),
       ("Nagpur", 21.10, 79.05, 42.6), ("Shimla", 31.10, 77.17, 24.5), ("Ahmedabad", 23.07, 72.63, 41.5)]
ref_e = elevations([(a, b) for _, a, b, _ in REF])
may = slice(idx[(5, 1)], idx[(5, 31)] + 1)
checks = []
for (name, la, lo, imd), e in zip(REF, ref_e):
    v, _ = at_point(la, lo, e)
    checks.append({"place": name, "elev_m": round(e), "may_normal_c": round(float(v[may].mean()), 1), "imd_station_approx_c": imd,
                   "diff_c": round(float(v[may].mean()) - imd, 1)})
json.dump({"n_districts": len(out), "interpolation": how, "valid_cells": len(cells), "may_checks": checks,
           "note": "IMD station values are approximate reference figures for a sanity check, not inputs."},
          open(os.path.join(OUT, "district_normals_checks.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps({"n": len(out), **how, "checks": checks}, indent=1))
