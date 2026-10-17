"""All-India district heat layer: exposure (ERA5 summers) + sensitivity (WorldPop 2025) for every district.

Inputs
  - District polygons: geoBoundaries IND ADM2 (source: Local Government Directory, Govt of India; ODbL 1.0) - 735 units,
    outline follows India's official boundary (Aksai Chin inside Leh; PoK/Gilgit-Baltistan present as 'DATA NOT AVAILABLE').
  - WorldPop Global2 R2025A 1 km age/sex structures, India: pop_2025 (total), t_00 (age 0-1), t_01 (1-4), t_65..t_90 (65+).
  - Open-Meteo historical weather API (ERA5 / ERA5-Land reanalysis), daily Tmax, Tmin, max wet-bulb, 1 Apr - 30 Jun 2021-2025,
    at each district's representative point.
  - State names: majority state of GeoNames populated places inside each polygon (data/india_places.tsv.gz).

Usage: python3 -I district_layer.py <site-packages> <adm2.geojson> <worldpop_dir> <cache_dir> <out_dir>
Outputs: <out_dir>/india_districts.geojson (simplified, with stats), india_district_stats.csv, india_district_checks.json
"""
import json
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import requests  # noqa: E402
from rasterio import features  # noqa: E402
from scipy.stats import rankdata, spearmanr  # noqa: E402

ADM2, POP, CACHE, OUT = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
os.makedirs(CACHE, exist_ok=True)
YEARS = [2021, 2022, 2023, 2024, 2025]
API = "https://archive-api.open-meteo.com/v1/archive"
DAILY = "temperature_2m_max,temperature_2m_min,wet_bulb_temperature_2m_max"

g = gpd.read_file(ADM2)[["shapeName", "shapeID", "geometry"]].rename(columns={"shapeName": "district", "shapeID": "id"})
g["no_data"] = g.district.eq("DATA NOT AVAILABLE")
g["area_km2"] = g.to_crs(6933).area / 1e6  # equal-area projection
rp = g.geometry.representative_point()
g["lat"], g["lon"] = rp.y.round(4), rp.x.round(4)

# ---------- state for each district (majority of GeoNames places inside it) ----------
pl = pd.read_csv(os.path.join(OUT, "india_places.tsv.gz"), sep="\t", usecols=["lat", "lon", "st"], dtype={"st": str}).dropna()
pts = gpd.GeoDataFrame(pl, geometry=gpd.points_from_xy(pl.lon, pl.lat), crs=4326)
j = gpd.sjoin(pts, g[["id", "geometry"]], predicate="within")
g["state"] = g.id.map(j.groupby("id").st.agg(lambda s: s.value_counts().index[0]))
for k in g.index[g.state.isna() & ~g.no_data]:  # tiny / island districts with no place inside the polygon: nearest place's state
    c = g.geometry[k].representative_point()
    g.at[k, "state"] = pl.st.iloc[int(np.argmin((pl.lat - c.y) ** 2 + (pl.lon - c.x) ** 2))]

# ---------- WorldPop zonal sums on the 1 km grid ----------
with rasterio.open(os.path.join(POP, "pop_2025.tif")) as r:
    shape, transform = (r.height, r.width), r.transform
    zone = features.rasterize(((geom, k + 1) for k, geom in enumerate(g.geometry)), out_shape=shape, transform=transform,
                              fill=0, dtype="int32")


def zsum(name):
    with rasterio.open(os.path.join(POP, name)) as r:
        a = r.read(1).astype("float64")
        a[(a < 0) | ~np.isfinite(a)] = 0
    return np.bincount(zone.ravel(), weights=a.ravel(), minlength=len(g) + 1)[1:]


g["pop_total"] = zsum("pop_2025.tif")
g["pop_under5"] = zsum("t_00_2025.tif") + zsum("t_01_2025.tif")
g["pop_65plus"] = sum(zsum(f"t_{a}_2025.tif") for a in (65, 70, 75, 80, 85, 90))
g["share_under5"] = g.pop_under5 / g.pop_total.where(g.pop_total > 0)
g["share_65plus"] = g.pop_65plus / g.pop_total.where(g.pop_total > 0)
g["density_per_km2"] = g.pop_total / g.area_km2

# ---------- where people live: population-weighted centre of each district ----------
# The polygon's representative point can sit on a glacier or in a desert far from any town (Leh's lies ~46 km from where
# its people live, at ~-4 C summer max). Heat exposure is taken where people are: the population-weighted centre, or the
# most populous 1 km cell if that centre falls outside the polygon. Within 15 km of the representative point the
# difference is below ERA5's grid spacing, so the representative point (already cached) is kept there.
with rasterio.open(os.path.join(POP, "pop_2025.tif")) as r:
    popa = r.read(1).astype("float64")
    popa[(popa < 0) | ~np.isfinite(popa)] = 0
rr, cc = np.indices(shape)
xs, ys = (np.asarray(v) for v in rasterio.transform.xy(transform, rr.ravel(), cc.ravel()))
zr, wr = zone.ravel(), popa.ravel()
sw = np.bincount(zr, weights=wr, minlength=len(g) + 1)
sx = np.bincount(zr, weights=wr * xs, minlength=len(g) + 1)
sy = np.bincount(zr, weights=wr * ys, minlength=len(g) + 1)
order = np.lexsort((-wr, zr))  # per zone, most populous cell first
first = {}
for i in order:
    first.setdefault(zr[i], i)
pt_lat, pt_lon, pt_kind = [], [], []
for k, geom in enumerate(g.geometry):
    la, lo, kind = g.lat[k], g.lon[k], "representative_point"
    if sw[k + 1] > 0:
        px, py = sx[k + 1] / sw[k + 1], sy[k + 1] / sw[k + 1]
        if not geom.contains(gpd.points_from_xy([px], [py])[0]):
            px, py = xs[first[k + 1]], ys[first[k + 1]]
        if 111 * np.hypot(py - la, (px - lo) * np.cos(np.radians(py))) > 15:
            la, lo, kind = round(float(py), 4), round(float(px), 4), "population_centre"
    pt_lat.append(la); pt_lon.append(lo); pt_kind.append(kind)
g["rp_lat"], g["rp_lon"] = g.lat, g.lon
g["lat"], g["lon"], g["point"] = pt_lat, pt_lon, pt_kind

# ---------- ERA5 summer climate at each district point (cached per point and year) ----------
live = g[~g.no_data].reset_index()
known = {}  # (year, lat, lon) -> daily dict
for y in YEARS:  # earlier runs cached 50-point batches in representative-point order
    for b0 in range(0, len(live), 50):
        path = os.path.join(CACHE, f"era5_{y}_{b0:04d}.json")
        if os.path.exists(path):
            data = json.load(open(path))
            data = data if isinstance(data, list) else [data]
            for (_, row), loc in zip(live.iloc[b0:b0 + 50].iterrows(), data):
                known[(y, row.rp_lat, row.rp_lon)] = loc["daily"]
    for path in sorted(p for p in os.listdir(CACHE) if p.startswith(f"era5pts_{y}_")):
        for item in json.load(open(os.path.join(CACHE, path))):
            known[(y, item["lat"], item["lon"])] = item["daily"]


def fetch(y, pts):
    params = {"latitude": ",".join(str(p[0]) for p in pts), "longitude": ",".join(str(p[1]) for p in pts), "daily": DAILY,
              "start_date": f"{y}-04-01", "end_date": f"{y}-06-30", "timezone": "Asia/Kolkata"}
    for attempt in range(8):
        try:
            resp = requests.get(API, params=params, timeout=180)
        except requests.exceptions.RequestException:
            time.sleep(20 * (attempt + 1))  # slow / dropped response: wait and retry
            continue
        if resp.status_code == 429:  # rate limit: back off
            time.sleep(30 * (attempt + 1))
            continue
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]
    raise SystemExit(f"Open-Meteo kept failing for {y}; cached points are kept, re-run to resume")


for y in YEARS:
    todo = [(row.lat, row.lon) for _, row in live.iterrows() if (y, row.lat, row.lon) not in known]
    todo = list(dict.fromkeys(todo))
    for b0 in range(0, len(todo), 50):
        pts = todo[b0:b0 + 50]
        got = fetch(y, pts)
        items = [{"lat": p[0], "lon": p[1], "daily": loc["daily"]} for p, loc in zip(pts, got)]
        json.dump(items, open(os.path.join(CACHE, f"era5pts_{y}_{len(os.listdir(CACHE)):04d}.json"), "w"))
        for it in items:
            known[(y, it["lat"], it["lon"])] = it["daily"]
        time.sleep(2)
rows = {k: [pd.DataFrame(known[(y, live.at[k, "lat"], live.at[k, "lon"])]) for y in YEARS] for k in live.index}
clim = []
for k, frames in rows.items():
    d = pd.concat(frames)
    tx, tn, wb = d.temperature_2m_max, d.temperature_2m_min, d.wet_bulb_temperature_2m_max
    clim.append({"id": live.at[k, "id"], "tmax_mean_c": tx.mean(), "tmin_mean_c": tn.mean(), "twb_max_mean_c": wb.mean(),
                 "days_tmax_ge40": (tx >= 40).sum() / len(YEARS), "tmax_p95_c": tx.quantile(0.95), "n_days": int(tx.notna().sum())})
g = g.merge(pd.DataFrame(clim), on="id", how="left")

# ---------- index: exposure + sensitivity (no adaptive-capacity data with India-wide coverage) ----------
ok = ~g.no_data & g.tmax_mean_c.notna() & (g.pop_total > 0)


def pr(s):  # percentile rank 0..1 among valid districts
    out = pd.Series(np.nan, index=s.index)
    out[ok] = (rankdata(s[ok]) - 1) / (ok.sum() - 1)
    return out


E_parts = {"tmax_mean_c": pr(g.tmax_mean_c), "tmin_mean_c": pr(g.tmin_mean_c), "twb_max_mean_c": pr(g.twb_max_mean_c),
           "days_tmax_ge40": pr(g.days_tmax_ge40)}
S_parts = {"share_65plus": pr(g.share_65plus), "share_under5": pr(g.share_under5), "density": pr(np.log10(g.density_per_km2 + 1))}
g["hx_E"] = pd.concat(E_parts, axis=1).mean(axis=1)
g["hx_S"] = pd.concat(S_parts, axis=1).mean(axis=1)
raw = (g.hx_E + g.hx_S) / 2
g["hx_index"] = pr(raw).round(3)
g["hx_rank"] = g.hx_index.rank(ascending=False, method="min")
g["hx_class"] = pd.cut(g.hx_index, [-0.01, 0.2, 0.4, 0.6, 0.8, 1.0], labels=["Very low", "Low", "Medium", "High", "Very high"]).astype(str)
g.loc[~ok, "hx_class"] = "No data"

# robustness check: equal weights vs first principal component of the 7 indicators
X = pd.concat({**E_parts, **S_parts}, axis=1)[ok]
Z = (X - X.mean()) / X.std()
w = np.linalg.eigh(np.cov(Z.T.values))[1][:, -1]
w = w if w.sum() > 0 else -w
pca_rank = Z.values @ w
rho = spearmanr(raw[ok], pca_rank).correlation
checks = {"n_districts": int(len(g)), "n_with_index": int(ok.sum()), "spearman_equal_vs_pca": round(float(rho), 3),
          "pca_weights": dict(zip(X.columns, np.round(w / np.abs(w).sum(), 3).tolist())),
          "pop_total_sum": int(g.pop_total.sum()), "years": YEARS, "season": "1 Apr - 30 Jun",
          "notes": ["Exposure uses reanalysis at one representative point per district (ERA5/ERA5-Land via Open-Meteo); "
                    "large districts are not uniform.",
                    "No adaptive-capacity indicator with all-India district coverage was available openly (NFHS-5 compiled "
                    "CSV covers 341 districts), so this is an exposure + sensitivity index, not a full vulnerability index.",
                    "District polygons: geoBoundaries IND ADM2 (LGD, 2021). Districts created after 2021 are not split out.",
                    "Weather point = where people live (population-weighted centre) when that is > 15 km from the polygon's "
                    "representative point; this matters in mountain and desert districts (e.g. Leh, Kachchh).",
                    "WorldPop age shares follow state-level age structures, so 65+ / under-5 shares vary little within a state.",
                    "In high mountains the reanalysis grid averages over surrounding peaks and reads colder than valley towns "
                    "(e.g. Leh, Kargil); these districts rank low either way."],
          "n_population_centre_points": int((g.point == "population_centre").sum())}
json.dump(checks, open(os.path.join(OUT, "india_district_checks.json"), "w"), indent=1)

cols = ["id", "district", "state", "lat", "lon", "point", "area_km2", "pop_total", "pop_under5", "pop_65plus", "share_under5",
        "share_65plus", "density_per_km2", "tmax_mean_c", "tmin_mean_c", "twb_max_mean_c", "days_tmax_ge40", "tmax_p95_c",
        "hx_E", "hx_S", "hx_index", "hx_rank", "hx_class", "no_data"]
stats = g[cols].copy()
for c in ["area_km2", "pop_total", "pop_under5", "pop_65plus", "density_per_km2"]:
    stats[c] = stats[c].round(0)
for c in ["share_under5", "share_65plus", "hx_E", "hx_S"]:
    stats[c] = stats[c].round(4)
for c in ["tmax_mean_c", "tmin_mean_c", "twb_max_mean_c", "days_tmax_ge40", "tmax_p95_c"]:
    stats[c] = stats[c].round(1)
stats.to_csv(os.path.join(OUT, "india_district_stats.csv"), index=False)
simp = g[["id", "geometry"]].copy()
simp["geometry"] = simp.geometry.simplify(0.01, preserve_topology=True)
simp = simp.merge(stats, on="id")
simp.to_file(os.path.join(OUT, "india_districts.geojson"), driver="GeoJSON", COORDINATE_PRECISION=4)
print(json.dumps(checks, indent=1))
