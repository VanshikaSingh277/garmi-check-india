"""Phase 2 - night surface heat (MODIS Aqua MYD11A2, ~01:30 local, 1 km, 8-day) and land cover (ESA WorldCover 2021, 10 m).

Sources (Microsoft Planetary Computer, free):
- modis-11A2-061: LST_Night_1km, scale 0.02 K; QC_Night bits 0-1 in {0,1} kept (good / other-quality) - NASA LP DAAC, public domain
- esa-worldcover (v200, 2021): classes 10 tree, 20 shrub, 30 grass, 40 crop, 50 built-up, 60 bare, 80 water, 90 wetland - CC BY 4.0
Pre-monsoon Apr-Jun 2021-2026, median of 8-day composites.

Usage: python modis_night_and_worldcover.py <pylib> <delhi_boundary.geojson> <out_dir>
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
b = gpd.read_file(BOUNDARY).to_crs(CRS)
bbox4326 = list(gpd.read_file(BOUNDARY).to_crs(4326).total_bounds)
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)


def grid(res):
    minx, miny, maxx, maxy = [round(v / res) * res for v in b.total_bounds]
    return from_origin(minx, maxy, res, res), int((maxx - minx) / res), int((maxy - miny) / res)


def read(href, tr, w, h, rs):
    with rasterio.open(href) as src, WarpedVRT(src, crs=CRS, transform=tr, width=w, height=h, resampling=rs) as v:
        return v.read(1)


def save(arr, name, tr, dtype="float32", nodata=np.nan):
    with rasterio.open(os.path.join(OUT, name), "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                       dtype=dtype, crs=CRS, transform=tr, nodata=nodata, compress="deflate") as d:
        d.write(arr.astype(dtype), 1)


# --- MODIS night LST at 1 km ---
tr, W, H = grid(1000.0)
items = [i for i in cat.search(collections=["modis-11A2-061"], bbox=bbox4326, datetime="2021-04-01/2026-06-30").items()
         if i.properties.get("platform") == "aqua" and int(i.properties["start_datetime"][5:7]) in (4, 5, 6)]
print("MODIS Aqua 8-day items:", len(items))
stack = []
for it in items:
    try:
        dn = read(it.assets["LST_Night_1km"].href, tr, W, H, Resampling.nearest).astype("float32")
        qc = read(it.assets["QC_Night"].href, tr, W, H, Resampling.nearest)
    except Exception as e:
        print("skip", it.id, str(e)[:60])
        continue
    lst = dn * 0.02 - 273.15
    lst[(dn == 0) | ((qc & 0b11) > 1)] = np.nan
    stack.append(lst)
night = np.nanmedian(np.stack(stack), axis=0)
save(night, "modis_lst_night_premonsoon_2021_2026_median.tif", tr)
v = night[np.isfinite(night)]
print("night LST: n items", len(stack), "| p5 %.1f p50 %.1f p95 %.1f degC" % tuple(np.percentile(v, [5, 50, 95])))

# --- ESA WorldCover 2021 at 10 m ---
tr10, W10, H10 = grid(10.0)
wc = [i for i in cat.search(collections=["esa-worldcover"], bbox=bbox4326).items() if "2021" in str(i.datetime) or "v200" in i.id]
print("WorldCover items:", [i.id for i in wc])
mosaic = np.zeros((H10, W10), dtype="uint8")
for it in wc:
    a = read(it.assets["map"].href, tr10, W10, H10, Resampling.nearest)
    mosaic = np.where(mosaic == 0, a, mosaic)
save(mosaic, "worldcover_2021_10m.tif", tr10, dtype="uint8", nodata=0)
vals, cnt = np.unique(mosaic[mosaic > 0], return_counts=True)
print("WorldCover class shares (bbox):", {int(k): round(float(c) / cnt.sum() * 100, 1) for k, c in zip(vals, cnt)})
