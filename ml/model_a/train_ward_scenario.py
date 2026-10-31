"""Ward cooling scenarios for Delhi: how much cooler a ward's surface gets if part of its built-up or bare land becomes tree cover.
Run from the repo root:  .venv/Scripts/python.exe -X utf8 ml/model_a/train_ward_scenario.py

Model: ward mean Landsat LST (pre-monsoon 2021-26, day and night) regressed on land-cover shares, with built-up land as the
reference. Physical sign constraints: tree and water cover can never make a ward warmer than built-up land. Linear, so every
coefficient can be read and checked; a monotone XGBoost was no better under the same validation (day MAE 0.60 vs 0.63 C).
Validation: leave-one-district-out (11 districts), so a ward is never predicted by a model that saw its own district.
Uncertainty: district-block bootstrap of the coefficients (10th-90th percentile).
Caveats: cross-sectional association, not a measured intervention; surface temperature, not air temperature; not for roofs
(Model A's albedo sign is unreliable here, so cool-roof effects come only from verified_numbers.csv)."""
import json
import os
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

R = os.path.join(os.path.dirname(__file__), "..", "..")
SRC = os.path.join(R, "data", "derived", "delhi_ward_features.csv")
OUT = os.path.join(R, "apps", "api", "data", "ward_scenario.json")
COVER = ["tree", "lowveg", "crop", "bare", "water"]
COOLER_THAN_BUILT = {"tree", "water"}
TARGETS = {"day": "lst_day_mean_c", "night": "lst_night_mean_c"}
BOOT = 500

d = pd.read_csv(SRC)
d["frac_lowveg"] = d.frac_shrub + d.frac_grass
X = np.c_[np.ones(len(d)), d[["frac_" + c for c in COVER]].values]
lb = np.full(X.shape[1], -np.inf)
ub = np.array([np.inf] + [0.0 if c in COOLER_THAN_BUILT else np.inf for c in COVER])
groups = d.district.values
rng = np.random.default_rng(20261029)


def fit(Xs, ys):
    return lsq_linear(Xs, ys, bounds=(lb, ub)).x


model = {}
for key, col in TARGETS.items():
    y = d[col].values
    err, base = [], []
    for g in np.unique(groups):
        tr, te = groups != g, groups == g
        err += list(np.abs(X[te] @ fit(X[tr], y[tr]) - y[te]))
        base += list(np.abs(y[tr].mean() - y[te]))
    coef = fit(X, y)
    names = np.unique(groups)
    boot = []
    for _ in range(BOOT):
        pick = rng.choice(names, size=len(names), replace=True)
        idx = np.concatenate([np.flatnonzero(groups == g) for g in pick])
        boot.append(fit(X[idx], y[idx]))
    boot = np.array(boot)
    model[key] = {
        "target": col,
        "intercept_c": round(float(coef[0]), 3),
        "per_share_c": {c: round(float(v), 3) for c, v in zip(COVER, coef[1:])},
        "per_share_p10_c": {c: round(float(v), 3) for c, v in zip(COVER, np.percentile(boot[:, 1:], 10, axis=0))},
        "per_share_p90_c": {c: round(float(v), 3) for c, v in zip(COVER, np.percentile(boot[:, 1:], 90, axis=0))},
        "cv_mae_c": round(float(np.mean(err)), 3),
        "baseline_mae_c": round(float(np.mean(base)), 3),
    }

wards = {r.ward_no: {"tree": round(float(r.frac_tree), 4), "built": round(float(r.frac_built), 4), "bare": round(float(r.frac_bare), 4)}
         for r in d.itertuples()}
card = {
    "about": "Ward cooling scenarios: change in ward mean surface temperature when built-up or bare land becomes tree cover. Built by ml/model_a/train_ward_scenario.py.",
    "trained": date.today().isoformat(),
    "data": "data/derived/delhi_ward_features.csv: Landsat LST pre-monsoon 2021-26 ward means; ESA WorldCover 2021 shares",
    "method": "Linear least squares, built-up as reference, tree and water constrained to be no warmer than built-up",
    "validation": "Leave-one-district-out (11 districts), mean absolute error",
    "uncertainty": f"District-block bootstrap, {BOOT} draws, 10th-90th percentile",
    "wards_n": len(d),
    "reference_cover": "built",
    "caveats": ["association_not_intervention", "surface_not_air", "not_for_roofs"],
    "model": model,
    "wards": wards,
}
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(card, f, indent=1)
for k, m in model.items():
    print(k, "CV MAE", m["cv_mae_c"], "vs baseline", m["baseline_mae_c"], "| tree", m["per_share_c"]["tree"],
          f"[{m['per_share_p10_c']['tree']}, {m['per_share_p90_c']['tree']}]", "| bare", m["per_share_c"]["bare"])
print("wrote", os.path.relpath(OUT, R))
