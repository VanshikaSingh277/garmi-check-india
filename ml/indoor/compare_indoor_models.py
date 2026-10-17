"""Phase 3 - Indoor temperature: do ML models beat the rule-based offsets?

Data: S1 South Asia indoor heat dataset (CC0) - Delhi, 56 homes, hourly means, 12 Apr - 30 Jun 2016.
Outdoor inputs, two settings:
  (a) 'station'  : the dataset's own weather station (best case)
  (b) 'forecast' : ERA5-Land at 28.6N 77.2E (what the live site will actually have)
Validation: GroupKFold by HOME (5 folds) -> the model never sees the test home.
Models: Rule (outdoor + median offset by roof group x hour, learned on training homes), Linear regression,
        Ridge, Random Forest, LightGBM, XGBoost.
Usage: python compare_indoor_models.py <pylib> <figshare_dir_with_pickles> <era5_2016_json> <out_dir>
"""
import ctypes
import glob
import json
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
for lib in glob.glob(os.path.join(sys.argv[1], "sklearn", ".dylibs", "libomp*.dylib")):
    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import lightgbm as lgb  # noqa: E402
import xgboost as xgb  # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402
from sklearn.linear_model import LinearRegression, Ridge  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

D, ERA, OUT = sys.argv[2], sys.argv[3], sys.argv[4]
os.makedirs(OUT, exist_ok=True)
ind = pd.read_pickle(f"{D}/_ind.pkl"); aws = pd.read_pickle(f"{D}/_aws.pkl"); h = pd.read_pickle(f"{D}/_h.pkl")
meta = ['Sr No', 'DD/MM/YYYY', 'Time', ind.columns[3], 'Hours', 'Month', 'Season', 'dt']
tc = [c for c in ind.columns if c not in meta and '(RH)' not in c and c != '10693000.1']
lg = ind[['dt'] + tc].melt(id_vars='dt', var_name='home', value_name='tin')
lg['tin'] = pd.to_numeric(lg.tin, errors='coerce'); lg = lg.dropna(); lg['home'] = lg.home.astype(str).str.strip()
lg['hr'] = lg.dt.dt.floor('h'); y = lg.groupby(['home', 'hr']).tin.mean().reset_index()
hh = h.set_index(h['Logger ID'].astype(str).str.strip())
y = y[y.home.map(lambda L: L in hh.index and str(hh.loc[L, 'Room type']).lower() != 'outside')]


def roof(L):
    r = hh.loc[L]; rs = str(r['Roof structure']).lower()
    if 'floor on top' in rs or str(r['Floor on top']).lower() == 'yes':
        return 'lower_floor'
    return 'tin_top' if 'tin' in rs else ('stone_slab_top' if 'stone' in rs else 'rcc_brick_top')


y['roof'] = y.home.map(roof)
y['floor'] = y.home.map(lambda L: pd.to_numeric(hh.loc[L, 'Floor'], errors='coerce'))
y['cooler'] = y.home.map(lambda L: 1 if str(hh.loc[L, 'Evaporative cooler']).lower() == 'yes' else 0)
y['fan'] = y.home.map(lambda L: 0 if str(hh.loc[L, 'Fan type']).lower() in ('no', 'unkown') else 1)


def outdoor(kind):
    if kind == 'station':
        a = aws[['dt']].copy()
        a['hr'] = a.dt.dt.floor('h') - pd.Timedelta(hours=1)   # stamp = end of averaged hour (gate review)
        for src, dst in [('Temp Out', 't'), ('Out Hum', 'rh'), ('Solar Rad.', 'sw'), ('Wind Speed', 'ws')]:
            a[dst] = pd.to_numeric(aws[src], errors='coerce')
    else:
        e = json.load(open(ERA))['hourly']
        a = pd.DataFrame({'hr': pd.to_datetime(e['time']), 't': e['temperature_2m'], 'rh': e['relative_humidity_2m'],
                          'sw': e['shortwave_radiation'], 'ws': e['wind_speed_10m']})
    a = a.drop(columns=[c for c in ['dt'] if c in a]).sort_values('hr').drop_duplicates('hr').set_index('hr').asfreq('h')
    for L in (1, 2, 3, 6, 12, 24):
        a[f't_lag{L}'] = a.t.shift(L)
    a['t_mean24'] = a.t.rolling(24, min_periods=18).mean(); a['t_max24'] = a.t.rolling(24, min_periods=18).max()
    a['sw_sum6'] = a.sw.rolling(6, min_periods=4).sum()
    return a.reset_index()


ROOFS = ['tin_top', 'stone_slab_top', 'rcc_brick_top', 'lower_floor']
results = []
for kind in ['station', 'forecast']:
    df = y.merge(outdoor(kind), on='hr', how='inner')
    df = df[(df.hr >= '2016-04-12') & (df.hr < '2016-07-01')].dropna()
    df['hod'] = df.hr.dt.hour
    df['hs'], df['hc'] = np.sin(2 * np.pi * df.hod / 24), np.cos(2 * np.pi * df.hod / 24)
    for r in ROOFS:
        df[f'roof_{r}'] = (df.roof == r).astype(int)
    feats = ['t', 'rh', 'sw', 'ws', 't_lag1', 't_lag2', 't_lag3', 't_lag6', 't_lag12', 't_lag24', 't_mean24', 't_max24', 'sw_sum6',
             'hs', 'hc', 'floor', 'cooler', 'fan'] + [f'roof_{r}' for r in ROOFS]
    X, Y, G = df[feats].values, df.tin.values, df.home.values
    aft, nig = df.hod.isin([14, 15, 16]).values, df.hod.isin([2, 3, 4, 5]).values
    models = {
        'Rule (outdoor + roof x hour median offset)': None,
        'Linear regression': lambda: LinearRegression(),
        'Ridge (alpha=10)': lambda: Ridge(alpha=10.0),
        'Random Forest': lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=20, n_jobs=-1, random_state=0),
        'LightGBM': lambda: lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0),
        'XGBoost': lambda: xgb.XGBRegressor(n_estimators=400, learning_rate=0.05, max_depth=6, subsample=0.8, colsample_bytree=0.8, min_child_weight=20, random_state=0, n_jobs=-1),
    }
    gkf = GroupKFold(n_splits=5)
    for name, mk in models.items():
        pred = np.zeros_like(Y); t0 = time.time()
        for tr, te in gkf.split(X, Y, G):
            if mk is None:
                d_tr = df.iloc[tr]; off = (d_tr.tin - d_tr.t).groupby([d_tr.roof, d_tr.hod]).median()
                d_te = df.iloc[te]
                pred[te] = d_te.t.values + np.array([off.get((r, hh_), 0.0) for r, hh_ in zip(d_te.roof, d_te.hod)])
            else:
                m = mk(); m.fit(X[tr], Y[tr]); pred[te] = m.predict(X[te])
        err = pred - Y
        results.append(dict(inputs=kind, model=name, MAE_all=np.abs(err).mean(), RMSE_all=np.sqrt((err ** 2).mean()),
                            MAE_afternoon=np.abs(err[aft]).mean(), MAE_night=np.abs(err[nig]).mean(),
                            bias=err.mean(), train_s=time.time() - t0, n_rows=len(Y), n_homes=len(set(G))))
        print(kind, name, f"MAE {np.abs(err).mean():.2f}", flush=True)
res = pd.DataFrame(results).round(3)
res.to_csv(os.path.join(OUT, "indoor_model_comparison.csv"), index=False)
print(res.to_string(index=False))
