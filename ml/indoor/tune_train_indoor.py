"""Phase 3 - tune + retrain the indoor model (XGBoost = best in compare_indoor_models.py), SHAP, export.

Features restricted to what the site can know: forecast weather (t, rh, sw, ws + lags) and the user's taps
(roof group incl. 'not top floor', fan yes/no, cooler yes/no). 'floor number' is NOT asked -> dropped.
Validation: GroupKFold by home (5 folds). Prediction interval: empirical 10th-90th pct of CV residuals.
Usage: python tune_train_indoor.py <pylib> <figshare_dir> <era5_2016_json> <out_dir>
"""
import ctypes, glob, itertools, json, os, sys, time
sys.path.insert(0, sys.argv[1])
for lib in glob.glob(os.path.join(sys.argv[1], "sklearn", ".dylibs", "libomp*.dylib")):
    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
import numpy as np, pandas as pd, xgboost as xgb, shap  # noqa: E401,E402
from sklearn.model_selection import GroupKFold  # noqa: E402

src = open(os.path.join(os.path.dirname(__file__), "compare_indoor_models.py")).read()
exec(src.split("ROOFS = [")[0])                    # reuse data loading + outdoor() from the comparison script
ROOFS = ['tin_top', 'stone_slab_top', 'rcc_brick_top', 'lower_floor']
df = y.merge(outdoor('forecast'), on='hr', how='inner')
df = df[(df.hr >= '2016-04-12') & (df.hr < '2016-07-01')].dropna()
df['hod'] = df.hr.dt.hour; df['hs'] = np.sin(2 * np.pi * df.hod / 24); df['hc'] = np.cos(2 * np.pi * df.hod / 24)
for r in ROOFS:
    df[f'roof_{r}'] = (df.roof == r).astype(int)
FEATS = ['t', 'rh', 'sw', 'ws', 't_lag1', 't_lag2', 't_lag3', 't_lag6', 't_lag12', 't_lag24', 't_mean24', 't_max24', 'sw_sum6',
         'hs', 'hc', 'cooler', 'fan'] + [f'roof_{r}' for r in ROOFS]
X, Y, G = df[FEATS], df.tin.values, df.home.values
gkf = GroupKFold(n_splits=5)


def cv(params):
    pred = np.zeros_like(Y)
    for tr, te in gkf.split(X, Y, G):
        m = xgb.XGBRegressor(**params, subsample=0.8, colsample_bytree=0.8, random_state=0, n_jobs=-1)
        m.fit(X.iloc[tr], Y[tr]); pred[te] = m.predict(X.iloc[te])
    return pred


grid = list(itertools.product([3, 4, 6], [0.03, 0.06], [300, 600], [20, 100]))
log = []
best = None
for md, lr, ne, mcw in grid:
    p = dict(max_depth=md, learning_rate=lr, n_estimators=ne, min_child_weight=mcw)
    t0 = time.time(); pr = cv(p); mae = float(np.abs(pr - Y).mean())
    log.append({**p, "cv_mae": round(mae, 4), "secs": round(time.time() - t0, 1)})
    if best is None or mae < best[0]:
        best = (mae, p, pr)
    print(p, round(mae, 3), flush=True)
mae, P, pred = best
res = pred - Y
aft, nig = df.hod.isin([14, 15, 16]).values, df.hod.isin([2, 3, 4, 5]).values
q10, q90 = np.percentile(res, [10, 90])
summary = {"best_params": P, "cv_mae_all": round(mae, 3), "cv_rmse_all": round(float(np.sqrt((res ** 2).mean())), 3),
           "cv_mae_afternoon": round(float(np.abs(res[aft]).mean()), 3), "cv_mae_night": round(float(np.abs(res[nig]).mean()), 3),
           "residual_p10": round(float(q10), 2), "residual_p90": round(float(q90), 2),
           "interval_note": "show predicted indoor temp with range [pred - p90, pred - p10] (80% empirical interval)",
           "n_homes": int(len(set(G))), "n_rows": int(len(Y)), "features": FEATS,
           "training_data": "S1 Tasgaonkar 2022 (CC0) Delhi 12 Apr-30 Jun 2016; outdoor = ERA5-Land t/rh + ERA5 sw/ws (Open-Meteo)",
           "validation": "GroupKFold(5) by home"}
final = xgb.XGBRegressor(**P, subsample=0.8, colsample_bytree=0.8, random_state=0, n_jobs=-1).fit(X, Y)
final.save_model(os.path.join(OUT, "indoor_xgb_model.json"))
ex = shap.TreeExplainer(final)
sv = ex.shap_values(X.sample(5000, random_state=0))
imp = pd.Series(np.abs(sv).mean(axis=0), index=FEATS).sort_values(ascending=False).round(3)
summary["shap_mean_abs_top"] = imp.head(12).to_dict()
# roof effect at 3 pm and 3 am (mean SHAP of each roof dummy when =1)
Xs = X.sample(20000, random_state=1); svs = ex.shap_values(Xs); sdf = pd.DataFrame(svs, columns=FEATS, index=Xs.index)
dfs = df.loc[Xs.index]
eff = {}
for r in ROOFS:
    for lbl, hrs in [("15h", [15]), ("03h", [3])]:
        msk = (dfs.roof == r) & dfs.hod.isin(hrs)
        eff[f"{r}@{lbl}"] = round(float(sdf.loc[msk, [f'roof_{x}' for x in ROOFS]].sum(axis=1).mean()), 2) if msk.any() else None
summary["shap_roof_contribution_degC"] = eff
json.dump(summary, open(os.path.join(OUT, "indoor_model_card.json"), "w"), indent=2)
pd.DataFrame(log).to_csv(os.path.join(OUT, "indoor_tuning_log.csv"), index=False)
print(json.dumps(summary, indent=2))
