"""Model A with physical direction constraints: what makes a place hot, where more trees or water can never mean hotter.

Data: data/cache/cities/<city>.npz from pipelines/satellite/city_grid.py (90 m cells; target = pre-monsoon Landsat LST).
Constraints (LightGBM monotone_constraints), only where the physics is unambiguous:
  cooler with more: tree share, NDVI, water share, MNDWI (wetness)    hotter with more: built share, NDBI, distance to water
  free: albedo (bright dry soil is hot in pre-monsoon Delhi, so its sign is confounded, see model_a_card.json), elevation
        (confounded with the forested Ridge), grass/shrub, crop and bare shares.
Validation: the same 5 km spatial-block GroupKFold for the free and the constrained model, so the cost of the constraints is
measured, not assumed. Physics checks on the fitted model: +10 points of tree cover in every cell must cool or leave every
cell unchanged; the same for +10 points of water; and per-feature contributions (LightGBM pred_contrib, i.e. TreeSHAP)
must have the constrained signs on average.
Usage (repo root):  .venv/Scripts/python.exe -X utf8 ml/model_a/train_model_a_monotone.py [city]
Writes ml/model_a/model_a_monotone_card.json and ml/model_a/model_a_monotone_<city>.txt"""
import json
import os
import sys
import time

import lightgbm as lgb
import numpy as np
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(__file__))
from physics_features import FEATS, SIGN  # noqa: E402

R = os.path.join(os.path.dirname(__file__), "..", "..")
CITY = sys.argv[1] if len(sys.argv) > 1 else "delhi"
OUT = os.path.dirname(__file__)
PARAMS = {"n_estimators": 400, "learning_rate": 0.03, "num_leaves": 63, "min_child_samples": 40, "subsample": 0.8,
          "subsample_freq": 1, "colsample_bytree": 0.9, "verbose": -1, "n_jobs": -1}

z = np.load(os.path.join(R, "data", "cache", "cities", f"{CITY}.npz"))
meta = json.loads(str(z["meta"]))
X = np.column_stack([z[f].ravel() for f in FEATS])
y = z["lst"].ravel()
ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
X, y = X[ok], y[ok]
h, w = z["lst"].shape
rows, cols = np.divmod(np.flatnonzero(ok), w)
cell = int(round(5000 / meta["res_m"]))
blocks = (rows // cell) * 10000 + cols // cell
print(CITY, "cells", len(y), "blocks", len(np.unique(blocks)), flush=True)


def model(constrained):
    mc = [SIGN.get(f, 0) for f in FEATS] if constrained else None
    return lgb.LGBMRegressor(**PARAMS, **({"monotone_constraints": mc, "monotone_constraints_method": "advanced"} if mc else {}))


res = {}
for name, cons in (("free", False), ("constrained", True)):
    pred, t0 = np.empty_like(y), time.time()
    for tr, te in GroupKFold(n_splits=5).split(X, y, blocks):
        pred[te] = model(cons).fit(X[tr], y[tr]).predict(X[te])
    err = pred - y
    res[name] = {"mae_c": round(float(np.abs(err).mean()), 3), "rmse_c": round(float(np.sqrt((err ** 2).mean())), 3),
                 "r2": round(float(1 - (err ** 2).sum() / ((y - y.mean()) ** 2).sum()), 3), "cv_seconds": round(time.time() - t0, 1)}
    print(name, res[name], flush=True)

final = model(True).fit(X, y)
base = final.predict(X)
checks = {}
for f, step in (("f_tree", 0.1), ("f_water", 0.1)):
    X2 = X.copy()
    i = FEATS.index(f)
    X2[:, i] = np.clip(X2[:, i] + step, 0, 1)
    d = final.predict(X2) - base
    checks[f"plus10pts_{f}"] = {"cells_warmer": int((d > 1e-6).sum()), "median_change_c": round(float(np.median(d)), 3),
                                "p10_change_c": round(float(np.percentile(d, 10)), 3)}
contrib = final.predict(X, pred_contrib=True)[:, :-1]
mean_c = {f: round(float(np.mean(contrib[:, i] * (X[:, i] - X[:, i].mean()))), 4) for i, f in enumerate(FEATS)}
signs_ok = {f: bool(np.sign(mean_c[f]) in (0, SIGN[f]) or mean_c[f] == 0) for f in SIGN}
importance = {f: round(float(np.abs(contrib[:, i]).mean()), 3) for i, f in enumerate(FEATS)}
final.booster_.save_model(os.path.join(OUT, f"model_a_monotone_{CITY}.txt"))
card = {"about": "Model A with physical direction constraints (ml/model_a/train_model_a_monotone.py)", "city": CITY,
        "data": f"pipelines/satellite/city_grid.py {CITY}: Landsat 8/9 LST Apr-Jun {meta['lst_years']}, {meta['lst_scenes']} scenes; "
                "SR indices 2025-26; ESA WorldCover 2021; Copernicus DEM; 90 m cells",
        "cells": int(len(y)), "features": FEATS, "constraints": SIGN, "params": PARAMS,
        "validation": "5 km spatial-block GroupKFold (5 folds), same folds for both models",
        "cv": res, "cost_of_constraints_mae_c": round(res["constrained"]["mae_c"] - res["free"]["mae_c"], 3),
        "physics_checks": {**checks, "constrained_signs_hold": signs_ok}, "mean_abs_contribution_c": importance,
        "caveats": ["surface_not_air", "not_for_roofs: albedo is unconstrained and confounded; cool-roof effects come only from verified_numbers.csv",
                    "association_not_intervention"]}
with open(os.path.join(OUT, f"model_a_monotone_card{'' if CITY == 'delhi' else '_' + CITY}.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(card, f, indent=1)
print(json.dumps({k: card[k] for k in ("cv", "cost_of_constraints_mae_c", "physics_checks")}, indent=1))
