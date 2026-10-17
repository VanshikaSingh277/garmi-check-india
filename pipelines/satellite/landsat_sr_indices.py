"""Phase 3 prep - Landsat 8/9 surface-reflectance median (Apr-Jun 2025-2026) -> NDVI, NDBI, MNDWI, broadband albedo (30 m).

Scaling (USGS C2 L2 SR): reflectance = DN * 0.0000275 - 0.2
Indices: NDVI=(NIR-R)/(NIR+R); NDBI=(SWIR1-NIR)/(SWIR1+NIR); MNDWI=(G-SWIR1)/(G+SWIR1)
Albedo: Liang (2001) shortwave broadband for Landsat: 0.356*B + 0.130*R + 0.373*NIR + 0.085*SWIR1 + 0.072*SWIR2 - 0.0018
        (Liang S. 2001, Remote Sens. Environ. 76:213-238) - used only as an ML feature.
Usage: python landsat_sr_indices.py <pylib> <delhi_boundary.geojson> <out_dir>
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
CRS, RES = "EPSG:32643", 30.0
b = gpd.read_file(BOUNDARY).to_crs(CRS)
minx, miny, maxx, maxy = [round(v / RES) * RES for v in b.total_bounds]
W, H = int((maxx - minx) / RES), int((maxy - miny) / RES)
TR = from_origin(minx, maxy, RES, RES)
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
bb = list(gpd.read_file(BOUNDARY).to_crs(4326).total_bounds)
items = [i for i in cat.search(collections=["landsat-c2-l2"], bbox=bb, datetime="2025-04-01/2026-06-30",
                               query={"eo:cloud_cover": {"lt": 10}, "platform": {"in": ["landsat-8", "landsat-9"]}}).items() if i.datetime.month in (4, 5, 6)]
print("scenes", len(items))
BANDS = ["blue", "green", "red", "nir08", "swir16", "swir22"]
BAD = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | 1
stacks = {k: [] for k in BANDS}


def rd(href, rs):
    with rasterio.open(href) as s, WarpedVRT(s, crs=CRS, transform=TR, width=W, height=H, resampling=rs) as v:
        return v.read(1)


for it in items:
    try:
        qa = rd(it.assets["qa_pixel"].href, Resampling.nearest)
        bad = (qa & BAD) != 0
        if (~bad & (qa > 0)).mean() < 0.3:
            continue
        for k in BANDS:
            a = rd(it.assets[k].href, Resampling.bilinear).astype("float32")
            r = a * 0.0000275 - 0.2
            r[bad | (a == 0)] = np.nan
            stacks[k].append(r)
        print("ok", it.id)
    except Exception as e:
        print("skip", it.id, str(e)[:60])
med = {k: np.nanmedian(np.stack(v), axis=0) for k, v in stacks.items()}
B, G, R, N, S1, S2 = (med[k] for k in BANDS)
out = {"ndvi": (N - R) / (N + R), "ndbi": (S1 - N) / (S1 + N), "mndwi": (G - S1) / (G + S1),
       "albedo": 0.356 * B + 0.130 * R + 0.373 * N + 0.085 * S1 + 0.072 * S2 - 0.0018}
for k, a in out.items():
    with rasterio.open(os.path.join(OUT, f"{k}_2025_2026_premonsoon.tif"), "w", driver="GTiff", width=W, height=H, count=1,
                       dtype="float32", crs=CRS, transform=TR, nodata=np.nan, compress="deflate") as d:
        d.write(a.astype("float32"), 1)
    v = a[np.isfinite(a)]
    print(k, "p5 %.3f p50 %.3f p95 %.3f" % tuple(np.percentile(v, [5, 50, 95])))
