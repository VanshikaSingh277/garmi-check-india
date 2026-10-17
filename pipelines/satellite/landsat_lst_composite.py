"""Phase 2 - pre-monsoon (Apr-Jun) Landsat 8/9 surface temperature composite for Delhi, 30 m.

Source: Landsat Collection 2 Level-2 (USGS; public domain) via Microsoft Planetary Computer STAC (free).
Scaling (USGS C2 L2 ST_B10 / 'lwir11'): K = DN * 0.00341802 + 149.0 ; degC = K - 273.15
Cloud mask: QA_PIXEL bits 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow -> masked; fill (bit 0) masked.
Method: per-year median of clear pixels, then median of yearly medians (2021-2026).
NOTE: this is SURFACE temperature (~10:30-11:00 local overpass), not air temperature.

Usage: python landsat_lst_composite.py <pylib> <delhi_boundary.geojson> <out_dir>
"""
import os
import sys

sys.path.insert(0, sys.argv[1])
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import planetary_computer  # noqa: E402
import pystac_client  # noqa: E402
import rasterio  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from rasterio.vrt import WarpedVRT  # noqa: E402

BOUNDARY, OUT = sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
CRS = "EPSG:32643"
RES = 30.0
b = gpd.read_file(BOUNDARY).to_crs(CRS)
minx, miny, maxx, maxy = [round(v / RES) * RES for v in b.total_bounds]
W, H = int((maxx - minx) / RES), int((maxy - miny) / RES)
TRANSFORM = from_origin(minx, maxy, RES, RES)
print("target grid", W, "x", H)

cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
bbox4326 = list(gpd.read_file(BOUNDARY).to_crs(4326).total_bounds)
items = [i for i in cat.search(collections=["landsat-c2-l2"], bbox=bbox4326, datetime="2021-04-01/2026-06-30",
                               query={"eo:cloud_cover": {"lt": 20}, "platform": {"in": ["landsat-8", "landsat-9"]}}).items()
         if i.datetime.month in (4, 5, 6)]
print("scenes:", len(items))

BAD = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | 1


def read(href, resampling):
    with rasterio.open(href) as src, WarpedVRT(src, crs=CRS, transform=TRANSFORM, width=W, height=H, resampling=resampling) as v:
        return v.read(1)


yearly = {}
log = []
for it in sorted(items, key=lambda x: x.datetime):
    try:
        st = read(it.assets["lwir11"].href, Resampling.bilinear).astype("float32")
        qa = read(it.assets["qa_pixel"].href, Resampling.nearest)
    except Exception as e:  # network hiccup: skip scene, log it
        log.append((it.id, "ERR " + str(e)[:80]))
        continue
    lst = st * 0.00341802 + 149.0 - 273.15
    lst[(st == 0) | ((qa & BAD) != 0)] = np.nan
    lst[(lst < 5) | (lst > 75)] = np.nan
    clear = float(np.isfinite(lst).mean())
    log.append((it.id, f"clear={clear:.2f}"))
    if clear < 0.05:
        continue
    yearly.setdefault(it.datetime.year, []).append(lst)
    print(it.id, f"clear {clear:.2f}")

meds = []
for y, arrs in sorted(yearly.items()):
    m = np.nanmedian(np.stack(arrs), axis=0).astype("float32")
    meds.append(m)
    with rasterio.open(os.path.join(OUT, f"lst_premonsoon_{y}.tif"), "w", driver="GTiff", width=W, height=H, count=1,
                       dtype="float32", crs=CRS, transform=TRANSFORM, nodata=np.nan, compress="deflate") as dst:
        dst.write(m, 1)
    print(y, "scenes", len(arrs), "median of medians so far")
comp = np.nanmedian(np.stack(meds), axis=0).astype("float32")
with rasterio.open(os.path.join(OUT, "lst_premonsoon_2021_2026_median.tif"), "w", driver="GTiff", width=W, height=H, count=1,
                   dtype="float32", crs=CRS, transform=TRANSFORM, nodata=np.nan, compress="deflate") as dst:
    dst.write(comp, 1)
open(os.path.join(OUT, "landsat_scene_log.txt"), "w").write("\n".join(f"{a}\t{b}" for a, b in log))
v = comp[np.isfinite(comp)]
print("composite: valid px", v.size, "| p5 %.1f p50 %.1f p95 %.1f degC" % tuple(np.percentile(v, [5, 50, 95])))
