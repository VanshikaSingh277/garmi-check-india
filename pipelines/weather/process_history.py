"""Phase 2 - derive Delhi weather/heat summaries from raw Open-Meteo ERA5-Land files.
Usage: python process_history.py <pylib> <raw_dir> <aws2016_pickle> <out_dir>"""
import glob, json, os, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
import numpy as np, pandas as pd
from heat_formulas import heat_index_c, wet_bulb_stull_c
RAW, AWS, OUT = sys.argv[2], sys.argv[3], sys.argv[4]
frames = []
for fn in glob.glob(os.path.join(RAW, "hourly_*.json")):
    d = json.load(open(fn)); h = d["hourly"]
    df = pd.DataFrame({"time": pd.to_datetime(h["time"]), "t": h["temperature_2m"], "rh": h["relative_humidity_2m"],
                       "wind": h["wind_speed_10m"], "sw": h["shortwave_radiation"]})
    la, lo = os.path.basename(fn)[7:-5].split("_"); df["lat"] = float(la); df["lon"] = float(lo); frames.append(df)
w = pd.concat(frames).dropna(subset=["t", "rh"])
w["hi"] = [heat_index_c(t, r) for t, r in zip(w.t, w.rh)]
w["twb"] = [wet_bulb_stull_c(t, r) for t, r in zip(w.t, w.rh)]
w["date"] = w.time.dt.date
daily = w.groupby(["lat", "lon", "date"]).agg(tmax=("t", "max"), tmin=("t", "min"), tmean=("t", "mean"),
                                               himax=("hi", "max"), twbmax=("twb", "max")).reset_index()
daily["date"] = pd.to_datetime(daily["date"]); daily["year"] = daily.date.dt.year
city = daily.groupby("date").agg(tmax=("tmax", "mean"), tmin=("tmin", "mean"), tmean=("tmean", "mean"),
                                 himax=("himax", "mean"), twbmax=("twbmax", "max")).reset_index()
city["year"] = city.date.dt.year
def band(x):
    return "red" if x > 55 else "orange" if x >= 46 else "yellow" if x >= 36 else "green"
city["imd_hi_band"] = city.himax.map(band)
summ = city[city.date.dt.month.isin([3, 4, 5, 6, 7, 8, 9])].groupby("year").agg(
    days=("date", "count"), tmax_peak=("tmax", "max"), tmin_peak=("tmin", "max"), hi_peak=("himax", "max"), twb_peak=("twbmax", "max"),
    days_tmax_ge40=("tmax", lambda s: int((s >= 40).sum())), days_tmax_ge45=("tmax", lambda s: int((s >= 45).sum())),
    nights_tmin_ge30=("tmin", lambda s: int((s >= 30).sum())),
    days_hi_orange_plus=("himax", lambda s: int((s >= 46).sum())), days_twb_ge30=("twbmax", lambda s: int((s >= 30).sum()))).round(1)
print("=== Delhi city-average (19 ERA5-Land points), Mar-Sep, by year ===\n", summ.to_string())
summ.to_csv(os.path.join(OUT, "weather_delhi_summer_summary_2021_2026.csv"))
city.to_csv(os.path.join(OUT, "weather_delhi_daily_city_2021_2026.csv"), index=False)
# spatial spread across grid points (pre-monsoon Apr-Jun means)
pm = daily[daily.date.dt.month.isin([4, 5, 6])].groupby(["lat", "lon"]).agg(tmax=("tmax", "mean"), tmin=("tmin", "mean"), himax=("himax", "mean")).round(2)
print("\n=== spread across Delhi grid, Apr-Jun mean daily max/min (degC) ===\n", pm.describe().loc[["min", "max", "std"]].to_string())
pm.to_csv(os.path.join(OUT, "weather_delhi_grid_premonsoon_means.csv"))
# de Bont 2024 definition: 97th percentile of daily MEAN temperature, 2008-2019
d = json.load(open(os.path.join(RAW, "daily_safdarjung_2008_2019.json")))["daily"]
dm = pd.Series(d["temperature_2m_mean"]).dropna()
p97 = dm.quantile(0.97); print(f"\n=== Delhi 97th pct daily mean temp 2008-2019 (ERA5-Land, Safdarjung point): {p97:.2f} degC (n={len(dm)}) ===")
json.dump({"p97_daily_mean_2008_2019_era5land": round(float(p97), 2), "n_days": int(len(dm))}, open(os.path.join(OUT, "delhi_p97_daily_mean.json"), "w"))
# validation vs 2016 Delhi AWS (S1 dataset)
v = json.load(open(os.path.join(RAW, "val_2016_28.6_77.2.json")))["hourly"]
e = pd.DataFrame({"hr": pd.to_datetime(v["time"]), "t_era": v["temperature_2m"], "rh_era": v["relative_humidity_2m"]})
aws = pd.read_pickle(AWS); aws["hr"] = aws["dt"].dt.floor("h"); aws["t_aws"] = pd.to_numeric(aws["Temp Out"], errors="coerce"); aws["rh_aws"] = pd.to_numeric(aws["Out Hum"], errors="coerce")
for shift in [0, -1]:
    a2 = aws[["hr", "t_aws", "rh_aws"]].copy(); a2["hr"] = a2.hr + pd.Timedelta(hours=shift)
    m = e.merge(a2, on="hr").dropna()
    dt = m.t_era - m.t_aws
    dmx = m.groupby(m.hr.dt.date).agg(era=("t_era", "max"), aws=("t_aws", "max")); dmn = m.groupby(m.hr.dt.date).agg(era=("t_era", "min"), aws=("t_aws", "min"))
    print(f"\nERA5-Land vs Delhi AWS 2016 (shift {shift}h, n={len(m)}): hourly bias {dt.mean():+.2f} C, MAE {dt.abs().mean():.2f} C, r={m.t_era.corr(m.t_aws):.3f}; "
          f"daily-max bias {(dmx.era-dmx.aws).mean():+.2f} C; daily-min bias {(dmn.era-dmn.aws).mean():+.2f} C; RH bias {(m.rh_era-m.rh_aws).mean():+.1f} pts")
