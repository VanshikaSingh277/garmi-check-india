"""Phase 3 - Model A: what makes a place hot? (pre-monsoon Landsat surface temperature, Delhi)

Target : Landsat 8/9 pre-monsoon LST composite (2021-2026), aggregated 30 m -> 90 m (~ native 100 m thermal).
Features (90 m): NDVI, NDBI, MNDWI, albedo (Landsat SR 2025-26 median), WorldCover 2021 fractions
                 (tree, grass+shrub, crop, built, bare, water), elevation (Copernicus DEM GLO-30), distance to water.
                 NO latitude/longitude (avoids spatial leakage - gate review lesson).
Validation: spatial block GroupKFold (5 km blocks, 5 folds). Models: Linear, Random Forest, LightGBM, XGBoost,
            HistGradientBoosting. Metrics: MAE, RMSE, R2, train time. Best -> small tuning grid -> SHAP -> per-ward drivers.
Usage: python train_model_a.py <pylib> <sat_dir> <wards.geojson> <out_dir>
"""
import ctypes, glob, json, os, sys, time
sys.path.insert(0, sys.argv[1])
for lib in glob.glob(os.path.join(sys.argv[1], "sklearn", ".dylibs", "libomp*.dylib")):
    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
import numpy as np, pandas as pd, rasterio, geopandas as gpd  # noqa: E401,E402
import planetary_computer, pystac_client  # noqa: E401,E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.vrt import WarpedVRT  # noqa: E402
from scipy.ndimage import distance_transform_edt  # noqa: E402
import lightgbm as lgb, xgboost as xgb, shap  # noqa: E401,E402
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

SAT, WARDS, OUT = sys.argv[2], sys.argv[3], sys.argv[4]
os.makedirs(OUT, exist_ok=True)
ref = rasterio.open(os.path.join(SAT, "lst_premonsoon_2021_2026_median.tif"))
T30, W30, H30, CRS = ref.transform, ref.width, ref.height, ref.crs
F = 3                                                    # 30 m -> 90 m
H, W = H30 // F, W30 // F
T90 = rasterio.Affine(T30.a * F, T30.b, T30.c, T30.d, T30.e * F, T30.f)


def agg30(path):
    a = rasterio.open(path).read(1).astype("float64")[:H * F, :W * F]
    return np.nanmean(a.reshape(H, F, W, F), axis=(1, 3))


lst = agg30(os.path.join(SAT, "lst_premonsoon_2021_2026_median.tif"))
feat = {k: agg30(os.path.join(SAT, f"{k}_2025_2026_premonsoon.tif")) for k in ["ndvi", "ndbi", "mndwi", "albedo"]}
with rasterio.open(os.path.join(SAT, "worldcover_2021_10m.tif")) as s, WarpedVRT(s, crs=CRS, transform=rasterio.Affine(10, 0, T90.c, 0, -10, T90.f), width=W * 9, height=H * 9, resampling=Resampling.nearest) as v:
    wc = v.read(1).reshape(H, 9, W, 9)
for code, name in [(10, "f_tree"), (20, "f_shrub"), (30, "f_grass"), (40, "f_crop"), (50, "f_built"), (60, "f_bare"), (80, "f_water")]:
    feat[name] = (wc == code).mean(axis=(1, 3))
feat["f_green_low"] = feat.pop("f_shrub") + feat.pop("f_grass")
feat["dist_water_m"] = distance_transform_edt(feat["f_water"] < 0.3) * 90.0
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
bb = list(gpd.GeoSeries.from_xy([T90.c, T90.c + W * 90], [T90.f - H * 90, T90.f], crs=CRS).to_crs(4326).total_bounds)
dem = np.full((H, W), np.nan)
for it in cat.search(collections=["cop-dem-glo-30"], bbox=bb).items():
    with rasterio.open(it.assets["data"].href) as s, WarpedVRT(s, crs=CRS, transform=T90, width=W, height=H, resampling=Resampling.average) as v:
        a = v.read(1).astype("float64"); a[a <= -1000] = np.nan
        dem = np.where(np.isnan(dem), a, dem)
feat["elevation_m"] = dem
wards = gpd.read_file(WARDS).to_crs(CRS)
wid = rasterize(((g, i + 1) for i, g in enumerate(wards.geometry)), out_shape=(H, W), transform=T90, fill=0, dtype="int32")
FEATS = ["ndvi", "ndbi", "mndwi", "albedo", "f_tree", "f_green_low", "f_crop", "f_built", "f_bare", "f_water", "dist_water_m", "elevation_m"]
rows, cols = np.nonzero(wid > 0)
df = pd.DataFrame({k: feat[k][rows, cols] for k in FEATS}); df["lst"] = lst[rows, cols]; df["ward_idx"] = wid[rows, cols] - 1
x_m, y_m = T90.c + (cols + 0.5) * 90, T90.f - (rows + 0.5) * 90
df["block"] = (np.floor(x_m / 5000)).astype(int) * 1000 + np.floor(y_m / 5000).astype(int)
df = df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
print("cells:", len(df), "| blocks:", df.block.nunique())
X, Y, G = df[FEATS].values, df.lst.values, df.block.values
gkf = GroupKFold(n_splits=5)
SKIP_COMPARE = os.environ.get("SKIP_COMPARE") == "1"
MODELS = {"Linear regression": lambda: LinearRegression(),
          "Random Forest": lambda: RandomForestRegressor(n_estimators=150, min_samples_leaf=10, max_features=0.5, n_jobs=-1, random_state=0),
          "LightGBM": lambda: lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0),
          "XGBoost": lambda: xgb.XGBRegressor(n_estimators=500, learning_rate=0.05, max_depth=7, subsample=0.8, colsample_bytree=0.8, min_child_weight=20, n_jobs=-1, random_state=0),
          "HistGradientBoosting": lambda: HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=63, random_state=0)}
res = []
for name, mk in ([] if SKIP_COMPARE else MODELS.items()):
    pred = np.zeros_like(Y); t0 = time.time()
    for tr, te in gkf.split(X, Y, G):
        m = mk(); m.fit(X[tr], Y[tr]); pred[te] = m.predict(X[te])
    e = pred - Y
    res.append(dict(model=name, spatial_cv_MAE=np.abs(e).mean(), RMSE=np.sqrt((e ** 2).mean()), R2=1 - (e ** 2).sum() / ((Y - Y.mean()) ** 2).sum(), train_s=time.time() - t0))
    print(res[-1], flush=True)
if SKIP_COMPARE:
    r = pd.read_csv(os.path.join(OUT, "model_a_comparison.csv"))
else:
    r = pd.DataFrame(res).round(3); r.to_csv(os.path.join(OUT, "model_a_comparison.csv"), index=False); print(r.to_string(index=False))
best = r.sort_values(["spatial_cv_MAE", "train_s"]).iloc[0].model
print("BEST:", best)
# small tuning grid for LightGBM / XGBoost family (whichever won); otherwise keep defaults
grid = [dict(n_estimators=n, learning_rate=lr, num_leaves=nl) for n in (400, 800) for lr in (0.03, 0.06) for nl in (31, 63)]
if SKIP_COMPARE:
    grid = [dict(n_estimators=400, learning_rate=0.03, num_leaves=63)]  # tuned winner from the full run (see model_a_card.json)
tune = []
if best in ("LightGBM", "XGBoost", "HistGradientBoosting"):
    for p in grid:
        pred = np.zeros_like(Y)
        for tr, te in gkf.split(X, Y, G):
            m = lgb.LGBMRegressor(**p, min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0)
            m.fit(X[tr], Y[tr]); pred[te] = m.predict(X[te])
        tune.append({**p, "spatial_cv_MAE": float(np.abs(pred - Y).mean())}); print(tune[-1], flush=True)
    P = min(tune, key=lambda d: d["spatial_cv_MAE"])
    final = lgb.LGBMRegressor(**{k: v for k, v in P.items() if k != "spatial_cv_MAE"}, min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0).fit(df[FEATS], Y)
    final.booster_.save_model(os.path.join(OUT, "model_a_lightgbm.txt"))
else:
    P = {}; final = MODELS[best]().fit(df[FEATS], Y)
ex = shap.TreeExplainer(final) if best != "Linear regression" else None
idx = df.sample(min(40000, len(df)), random_state=0).index
sv = ex.shap_values(df.loc[idx, FEATS])
glob_imp = pd.Series(np.abs(sv).mean(axis=0), index=FEATS).sort_values(ascending=False)
sdf = pd.DataFrame(sv, columns=FEATS, index=idx); sdf["ward_idx"] = df.loc[idx, "ward_idx"]
ward_drivers = sdf.groupby("ward_idx")[FEATS].mean()
top3 = ward_drivers.apply(lambda s: list(s.sort_values(ascending=False).index[:3]), axis=1)
wout = pd.DataFrame({"ward_no": wards.Ward_No.values[ward_drivers.index], "top3_heat_drivers": top3.values})
wout.to_csv(os.path.join(OUT, "ward_top3_heat_drivers.csv"), index=False)
wd = ward_drivers.copy(); wd.insert(0, "ward_no", wards.Ward_No.values[ward_drivers.index]); wd.round(3).to_csv(os.path.join(OUT, "ward_mean_shap.csv"), index=False)
dirn = {f: float(np.corrcoef(df.loc[idx, f], sdf[f])[0, 1]) for f in FEATS}
card = {"target": "Landsat pre-monsoon LST 2021-2026 (90 m)", "n_cells": int(len(df)), "validation": "spatial block GroupKFold 5 km, 5 folds",
        "comparison": r.to_dict("records"), "best": best, "tuned_params": P, "shap_mean_abs": glob_imp.round(3).to_dict(),
        "shap_direction_corr(feature,shap)": {k: round(v, 2) for k, v in dirn.items()},
        "sanity": "expect: ndvi/tree/water negative (cooler), built/ndbi positive (hotter)"}
json.dump(card, open(os.path.join(OUT, "model_a_card.json"), "w"), indent=2, default=str)
print(json.dumps({k: card[k] for k in ["best", "tuned_params", "shap_mean_abs", "shap_direction_corr(feature,shap)"]}, indent=2, default=str))
