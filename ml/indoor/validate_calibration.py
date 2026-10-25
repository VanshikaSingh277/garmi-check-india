"""Does per-home calibration improve the room estimate? (BACKEND_SPEC §7.4: ship only if MAE improves.)

Replays the 2016 Delhi homes with the shipped model's settings and GroupKFold(5) by home, so every home is predicted by
a model that never saw it. Then, for each held-out home, a family is simulated entering one day reading (15:00) and
one night reading (03:00) a day for its first N days. The calibration is the spec's: separate day and night biases,
shrunk towards 0 with k = within-home residual variance / between-home variance of home mean residuals, residuals
clipped at +/-3 MAD of the home's own readings, applied only once n >= 2, no kitchen readings. Error is measured on
every hour of the home's later days.

Usage: python validate_calibration.py <figshare_dir_with_pickles> <era5_2016_json> <model_card_json_to_update>
(The pickles come from ml/phase0/01_load_and_check.py; the ERA5 json from the Open-Meteo archive, 28.6N 77.2E.)"""
import json
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupKFold

D, ERA, CARD = sys.argv[1], sys.argv[2], sys.argv[3]
card = json.load(open(CARD, encoding="utf-8"))
ind, h = pd.read_pickle(f"{D}/_ind.pkl"), pd.read_pickle(f"{D}/_h.pkl")

# ---- the same data preparation as compare_indoor_models.py / tune_train_indoor.py
meta = ["Sr No", "DD/MM/YYYY", "Time", ind.columns[3], "Hours", "Month", "Season", "dt"]
tc = [c for c in ind.columns if c not in meta and "(RH)" not in c and c != "10693000.1"]
lg = ind[["dt"] + tc].melt(id_vars="dt", var_name="home", value_name="tin")
lg["tin"] = pd.to_numeric(lg.tin, errors="coerce")
lg = lg.dropna()
lg["home"] = lg.home.astype(str).str.strip()
lg["hr"] = lg.dt.dt.floor("h")
y = lg.groupby(["home", "hr"]).tin.mean().reset_index()
hh = h.set_index(h["Logger ID"].astype(str).str.strip())
y = y[y.home.map(lambda L: L in hh.index and str(hh.loc[L, "Room type"]).lower() != "outside")]


def roof(L):
    r = hh.loc[L]
    rs = str(r["Roof structure"]).lower()
    if "floor on top" in rs or str(r["Floor on top"]).lower() == "yes":
        return "lower_floor"
    return "tin_top" if "tin" in rs else ("stone_slab_top" if "stone" in rs else "rcc_brick_top")


y["roof"] = y.home.map(roof)
y["cooler"] = y.home.map(lambda L: 1 if str(hh.loc[L, "Evaporative cooler"]).lower() == "yes" else 0)
y["fan"] = y.home.map(lambda L: 0 if str(hh.loc[L, "Fan type"]).lower() in ("no", "unkown") else 1)
y["kitchen"] = y.home.map(lambda L: "kitchen" in str(hh.loc[L, "Room type"]).lower())

e = json.load(open(ERA))["hourly"]
a = pd.DataFrame({"hr": pd.to_datetime(e["time"]), "t": e["temperature_2m"], "rh": e["relative_humidity_2m"],
                  "sw": e["shortwave_radiation"], "ws": e["wind_speed_10m"]}).sort_values("hr").drop_duplicates("hr").set_index("hr").asfreq("h")
for L in (1, 2, 3, 6, 12, 24):
    a[f"t_lag{L}"] = a.t.shift(L)
a["t_mean24"] = a.t.rolling(24, min_periods=18).mean()
a["t_max24"] = a.t.rolling(24, min_periods=18).max()
a["sw_sum6"] = a.sw.rolling(6, min_periods=4).sum()
df = y.merge(a.reset_index(), on="hr", how="inner")
df = df[(df.hr >= "2016-04-12") & (df.hr < "2016-07-01")].dropna().reset_index(drop=True)
df["hod"] = df.hr.dt.hour
df["hs"], df["hc"] = np.sin(2 * np.pi * df.hod / 24), np.cos(2 * np.pi * df.hod / 24)
ROOFS = ["tin_top", "stone_slab_top", "rcc_brick_top", "lower_floor"]
for r in ROOFS:
    df[f"roof_{r}"] = (df.roof == r).astype(int)
FEATS = card["features"]
X, Y, G = df[FEATS], df.tin.values, df.home.values

# ---- out-of-fold predictions with the shipped settings
pred = np.zeros_like(Y)
for tr, te in GroupKFold(n_splits=5).split(X, Y, G):
    m = xgb.XGBRegressor(**card["best_params"], subsample=0.8, colsample_bytree=0.8, random_state=0, n_jobs=2)
    m.fit(X.iloc[tr], Y[tr])
    pred[te] = m.predict(X.iloc[te])
df["pred"], df["res"] = pred, Y - pred                            # residual = indoor - predicted (the bias a reading measures)
df["period"] = np.where(df.hod.between(6, 17), "day", "night")
oof_mae = float(np.abs(df.res).mean())

# ---- shrinkage strength per period, from the residual structure (DETAILS §4.3)
k = {}
for per, g in df.groupby("period"):
    within = g.groupby("home").res.var().mean()
    between = g.groupby("home").res.mean().var()
    k[per] = float(within / between) if between > 0 else float("inf")


def calibrate(readings: np.ndarray, kk: float) -> float:
    """Shrunk mean bias of a home's readings, residuals clipped at +/-3 MAD (spec §7.4); 0 below 2 readings."""
    n = len(readings)
    if n < 2:
        return 0.0
    med = np.median(readings)
    mad = np.median(np.abs(readings - med))
    if mad > 0:
        readings = np.clip(readings, med - 3 * mad, med + 3 * mad)
    return float(readings.sum() / (n + kk))


rows = []
for N in (2, 3, 5, 7, 10, 14):
    raw_err, cal_err, homes = [], [], 0
    for home, g in df[~df.kitchen].groupby("home"):
        days = sorted(g.hr.dt.date.unique())
        if len(days) < N + 7:
            continue
        first, later = set(days[:N]), g[g.hr.dt.date > days[N - 1]]
        fit = g[g.hr.dt.date.isin(first)]
        bias = {"day": calibrate(fit[fit.hod == 15].res.values, k["day"]), "night": calibrate(fit[fit.hod == 3].res.values, k["night"])}
        corr = later.pred + later.period.map(bias)
        raw_err.append(np.abs(later.tin - later.pred).values)
        cal_err.append(np.abs(later.tin - corr).values)
        homes += 1
    raw, cal = float(np.concatenate(raw_err).mean()), float(np.concatenate(cal_err).mean())
    rows.append({"days_of_readings": N, "homes": homes, "mae_model_c": round(raw, 3), "mae_calibrated_c": round(cal, 3),
                 "change_c": round(cal - raw, 3)})

improves = all(r["change_c"] < 0 for r in rows)
card["calibration"] = {
    "method": "per-home day and night bias, shrunk with k, residuals clipped at +/-3 MAD, applied from n >= 2, no kitchen readings (BACKEND_SPEC §7.4)",
    "k_day": round(k["day"], 3), "k_night": round(k["night"], 3), "oof_mae_c": round(oof_mae, 3),
    "replay": rows, "readings_simulated": "one at 15:00 and one at 03:00 per day for the first N days; error on every hour of later days",
    "decision": "ship (MAE improves at every N)" if improves else "do not ship (MAE does not improve at every N)",
    "validated_on": "S1 Tasgaonkar 2022 (CC0) Delhi 2016, GroupKFold(5) by home, outdoor = ERA5 (Open-Meteo archive)",
}
with open(CARD, "w", encoding="utf-8") as f:
    json.dump(card, f, indent=1)
print(json.dumps(card["calibration"], indent=1))
