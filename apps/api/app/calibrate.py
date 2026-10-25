"""Learning each home from its readings (spec §7.4). Separate day and night biases (indoor - predicted), shrunk towards 0
with the k values validated in the model card (`calibration`), residuals clipped at +/-3 MAD of the home's own
readings, applied only once n >= 2, kitchen readings never used, last 30 days only.
Validation (ml/indoor/validate_calibration.py, recorded in the model card): it is applied only if the card says
"ship"; on the 2016 Delhi replay it lowered MAE at every number of reading days."""
import json
import os
from datetime import timedelta
from functools import lru_cache
from statistics import median, pstdev

from sqlalchemy import select

from . import config, db
from .models import Household, Reading

CARD = os.path.join(os.path.dirname(__file__), "..", "data", "indoor_model_card.json")
DAY_HOURS = range(6, 18)            # 06:00-17:59 is "day", the rest "night" (the split used in the validation)


@lru_cache(maxsize=1)
def validated() -> dict | None:
    with open(CARD, encoding="utf-8") as f:
        c = json.load(f).get("calibration")
    return c if c and c.get("decision", "").startswith("ship") else None


def period(hour: int) -> str:
    return "day" if hour in DAY_HOURS else "night"


def shrunk_bias(residuals: list[float], k: float) -> float | None:
    n = len(residuals)
    if n < 2:
        return None
    med = median(residuals)
    mad = median(abs(r - med) for r in residuals)
    clipped = [min(max(r, med - 3 * mad), med + 3 * mad) for r in residuals] if mad > 0 else list(residuals)
    return round(sum(clipped) / (n + k), 2)


def outlier(residual: float, others: list[float]) -> bool:
    """Once a home has 5 readings, flag (never drop) one more than 3 MAD from the home's median."""
    if len(others) < 5:
        return False
    med = median(others)
    mad = median(abs(r - med) for r in others)
    return mad > 0 and abs(residual - med) > 3 * mad


def recompute(s, h: Household) -> dict:
    """Update the home's calib_* fields from its usable readings of the last 30 days."""
    since = db.utcnow() - timedelta(days=config.CALIBRATION_WINDOW_DAYS)
    rows = s.scalars(select(Reading).where(Reading.household_id == h.id, Reading.used_for_calibration.is_(True), Reading.ts >= since)).all()
    res = {"day": [r.indoor_c - r.predicted_c for r in rows if r.period == "day" and r.predicted_c is not None],
           "night": [r.indoor_c - r.predicted_c for r in rows if r.period == "night" and r.predicted_c is not None]}
    v = validated()
    h.calib_n_day, h.calib_n_night = len(res["day"]), len(res["night"])
    h.calib_bias_day_c = shrunk_bias(res["day"], v["k_day"]) if v else None
    h.calib_bias_night_c = shrunk_bias(res["night"], v["k_night"]) if v else None
    every = res["day"] + res["night"]
    h.calib_sd_c = round(pstdev(every), 2) if len(every) >= 2 else None
    return summary(h)


def summary(h: Household) -> dict:
    applied = validated() is not None and (h.calib_bias_day_c is not None or h.calib_bias_night_c is not None)
    return {"applied": applied, "n_day": h.calib_n_day, "n_night": h.calib_n_night, "bias_day_c": h.calib_bias_day_c,
            "bias_night_c": h.calib_bias_night_c, "sd_c": h.calib_sd_c, "validated": validated() is not None}


def apply(hours: list[dict], h: Household) -> list[dict]:
    """Shift the room estimate by the home's bias for each hour's period (the range keeps its width)."""
    if validated() is None:
        return hours
    out = []
    for r in hours:
        b = h.calib_bias_day_c if period(int(r["time"][11:13])) == "day" else h.calib_bias_night_c
        out.append(r if not b else {**r, "indoor": round(r["indoor"] + b, 1), "low": round(r["low"] + b, 1), "high": round(r["high"] + b, 1)})
    return out
