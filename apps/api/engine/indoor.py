"""Indoor temperature estimate: XGBoost trained on 56 measured Delhi homes (2016, CC0 dataset), leave-home-out MAE 1.52 C.
Shown ALWAYS as a range (80 % empirical band from cross-validation residuals), never a single number."""
import json
import math
import os
from functools import lru_cache

import numpy as np
import xgboost as xgb

HERE = os.path.dirname(__file__)
MODEL = os.path.join(HERE, "..", "data", "indoor_xgb_model.json")
CARD = os.path.join(HERE, "..", "data", "indoor_model_card.json")
ROOFS = ["tin_top", "stone_slab_top", "rcc_brick_top", "lower_floor"]


@lru_cache(maxsize=1)
def _model():
    m = xgb.XGBRegressor()
    m.load_model(MODEL)
    return m, json.load(open(CARD))


def predict(hourly: list, start_index: int, roof: str, fan: bool, cooler: bool, hours: int = 24) -> list:
    m, card = _model()
    feats = card["features"]
    t = [r["t"] for r in hourly]
    out = []
    for k in range(start_index, min(start_index + hours, len(hourly))):
        if k < 24:
            continue
        r = hourly[k]
        hod = int(r["time"][11:13])
        win = t[k - 23:k + 1]
        row = {"t": r["t"], "rh": r["rh"], "sw": r["sw"], "ws": r["ws"],
               "t_lag1": t[k - 1], "t_lag2": t[k - 2], "t_lag3": t[k - 3], "t_lag6": t[k - 6], "t_lag12": t[k - 12], "t_lag24": t[k - 24],
               "t_mean24": float(np.mean(win)), "t_max24": float(np.max(win)),
               "sw_sum6": float(sum(x["sw"] for x in hourly[k - 5:k + 1])),
               "hs": math.sin(2 * math.pi * hod / 24), "hc": math.cos(2 * math.pi * hod / 24),
               "cooler": 1 if cooler else 0, "fan": 1 if fan else 0}
        for rf in ROOFS:
            row[f"roof_{rf}"] = 1 if rf == roof else 0
        x = np.array([[row[f] for f in feats]])
        p = float(m.predict(x)[0])
        out.append({"time": r["time"], "indoor": round(p, 1), "low": round(p - card["residual_p90"], 1),
                    "high": round(p - card["residual_p10"], 1), "outdoor": r["t"], "rh": r["rh"]})
    return out


def applicability(next24: list, in_delhi: bool) -> dict:
    """Is the forecast inside the conditions the model learned from? (training-range check from the model card)"""
    _, card = _model()
    a = card["applicability"]
    hours = [r for r in next24 if r.get("t") is not None and r.get("rh") is not None]
    inside = [a["t_c"][0] <= r["t"] <= a["t_c"][1] and a["rh_pct"][0] <= r["rh"] <= a["rh_pct"][1] for r in hours]
    share = round(sum(inside) / len(inside), 2) if inside else 0.0
    return {"ok": share >= a["min_share_in_range"], "share_in_range": share, "trained_t_c": a["t_c"], "trained_rh_pct": a["rh_pct"],
            "validated_here": bool(in_delhi), "basis": a["basis"]}


def model_info() -> dict:
    _, card = _model()
    return {"mae_c": card["cv_mae_all"], "band": [card["residual_p10"], card["residual_p90"]], "homes": card["n_homes"],
            "data": card["training_data"], "validation": card["validation"]}
