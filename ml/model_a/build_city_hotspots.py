"""City hotspots beyond Delhi: 1 km cells of pre-monsoon surface temperature with the main reasons each cell is hotter than
its city's average, for every city grid built by pipelines/satellite/city_grid.py.

Per city: a physically constrained LightGBM (same features and constraints as train_model_a_monotone.py) is checked with
5 km spatial-block CV, then refit; per-cell feature contributions (TreeSHAP via pred_contrib) are averaged over each 1 km
block (11 x 11 cells of 90 m). Drivers are the features adding more than 0.05 C over the city's average, as for Delhi wards.
The hottest blocks are named with the GeoNames locality nearest their centre.
Usage (repo root):  .venv/Scripts/python.exe -X utf8 ml/model_a/build_city_hotspots.py
Writes apps/api/data/city_hotspots.json (then rebuild the data manifest)."""
import glob
import json
import os
import sys

import lightgbm as lgb
import numpy as np
from sklearn.model_selection import GroupKFold

R = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(R, "apps", "api"))
from engine import places  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from physics_features import FEATS, SIGN  # noqa: E402

OUT = os.path.join(R, "apps", "api", "data", "city_hotspots.json")
BLOCK = 11
WORDS = {"ndbi": "built_paved", "f_built": "dense_buildings", "f_tree": "few_trees", "ndvi": "little_greenery", "mndwi": "dry_surfaces",
         "f_water": "no_water", "dist_water": "far_from_water", "albedo": "bright_dry_ground", "f_bare": "bare_ground",
         "elevation": "low_lying", "f_crop": "farmland_effect", "f_lowveg": "dry_grass_scrub"}
PARAMS = {"n_estimators": 250, "learning_rate": 0.05, "num_leaves": 63, "min_child_samples": 40, "subsample": 0.8, "subsample_freq": 1,
          "colsample_bytree": 0.9, "verbose": -1, "n_jobs": -1, "monotone_constraints": [SIGN.get(f, 0) for f in FEATS],
          "monotone_constraints_method": "advanced"}


def city(path):
    z = np.load(path)
    meta = json.loads(str(z["meta"]))
    h, w = z["lst"].shape
    F = np.stack([z[f] for f in FEATS], axis=-1)
    lst = z["lst"]
    ok = np.isfinite(lst) & np.isfinite(F).all(axis=-1)
    X, y = F[ok], lst[ok]
    r, c = np.nonzero(ok)
    cell = int(round(5000 / meta["res_m"]))
    groups = (r // cell) * 10000 + c // cell
    pred = np.empty_like(y)
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        pred[te] = lgb.LGBMRegressor(**PARAMS).fit(X[tr], y[tr]).predict(X[te])
    mae = float(np.abs(pred - y).mean())
    base_mae = float(np.abs(y - np.median(y)).mean())
    model = lgb.LGBMRegressor(**PARAMS).fit(X, y)
    contrib = np.full(lst.shape + (len(FEATS),), np.nan, "float32")
    contrib[ok] = model.predict(X, pred_contrib=True)[:, :-1]
    med = float(np.median(y))

    cells = []
    for i0 in range(0, h - BLOCK + 1, BLOCK):
        for j0 in range(0, w - BLOCK + 1, BLOCK):
            m = ok[i0:i0 + BLOCK, j0:j0 + BLOCK]
            if m.mean() < 0.5:
                continue
            sl = (slice(i0, i0 + BLOCK), slice(j0, j0 + BLOCK))
            mc = np.nanmean(contrib[sl][m], axis=0)
            drivers = [WORDS[FEATS[k]] for k in np.argsort(-mc) if mc[k] > 0.05][:3]
            cells.append({"lat": round(float(z["lat"][sl][m].mean()), 4), "lon": round(float(z["lon"][sl][m].mean()), 4),
                          "lst_c": round(float(lst[sl][m].mean()), 1), "vs_city_c": round(float(lst[sl][m].mean()) - med, 1),
                          "tree": round(float(z["f_tree"][sl][m].mean()), 3), "built": round(float(z["f_built"][sl][m].mean()), 3),
                          "water": round(float(z["f_water"][sl][m].mean()), 3), "drivers": drivers})
    hot, seen = [], set()
    for cl in sorted(cells, key=lambda x: -x["lst_c"]):
        d = places.describe(cl["lat"], cl["lon"])
        name = d.get("locality") or d.get("town")
        if not name or name in seen:
            continue
        seen.add(name)
        hot.append({**cl, "place": name, "place_km": d.get("locality_km")})
        if len(hot) == 20:
            break
    lsts = np.array([cl["lst_c"] for cl in cells])
    return meta["city"], {
        "name": meta["name"], "cells_km": round(BLOCK * meta["res_m"] / 1000, 2), "cells": cells, "hottest": hot,
        "lst_median_c": round(med, 1), "lst_p90_block_c": round(float(np.percentile(lsts, 90)), 1),
        "lst_scenes": meta["lst_scenes"], "lst_years": meta["lst_years"],
        "model": {"cv_mae_c": round(mae, 2), "baseline_mae_c": round(base_mae, 2), "cells_90m": int(len(y))}}


out = {"about": "City surface-heat hotspots, 1 km cells (ml/model_a/build_city_hotspots.py)",
       "source": "Landsat 8/9 C2 L2 surface temperature, pre-monsoon (Apr-Jun) median; drivers from a physically constrained LightGBM",
       "caveats": ["surface_not_air", "association_not_intervention", "not_for_roofs"], "features": FEATS, "constraints": SIGN, "cities": {}}
for p in sorted(glob.glob(os.path.join(R, "data", "cache", "cities", "*.npz"))):
    key, data = city(p)
    out["cities"][key] = data
    print(key, len(data["cells"]), "cells | CV MAE", data["model"]["cv_mae_c"], "vs", data["model"]["baseline_mae_c"],
          "| hottest:", ", ".join(h["place"] for h in data["hottest"][:5]), flush=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print("wrote", os.path.relpath(OUT, R), round(os.path.getsize(OUT) / 1e6, 2), "MB")
