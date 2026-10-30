"""Physical bounds on the room model (engine/indoor.physics_check): a passive home can't be colder than its coldest heat
sink or hotter than the past day's air plus the measured roof gain. Real forecasts must pass; impossible hours must not."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import indoor, weather  # noqa: E402
from tests.test_api_fixes import fake_forecast, status  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ROOFS = ["tin_top", "stone_slab_top", "rcc_brick_top", "lower_floor"]


def hourly(name):
    with open(os.path.join(FIX, f"openmeteo_{name}.json"), encoding="utf-8") as f:
        d = weather.parse_open_meteo(json.load(f))
    return [{**r, "twb": round(weather.wet_bulb_c(r["t"], r["rh"]), 1)} for r in d["hourly"]]


def test_model_predictions_on_recorded_weather_are_physical():
    for name in ["delhi", "delhi_2024-05-28", "jaisalmer", "chennai"]:
        h = hourly(name)
        for roof in ROOFS:
            for fan, cooler in [(False, False), (True, False), (True, True)]:
                preds = indoor.predict(h, 24, roof, fan, cooler, hours=len(h))
                assert indoor.physics_check(h, preds, roof, cooler) == [], (name, roof, fan, cooler)


def test_extrapolation_far_outside_training_is_caught():
    # Shimla's 6-17 C air is far below the 22-42 C the model learned from; it then predicts rooms near 28 C with no heat
    # source. The training-range gate already keeps these numbers out of the app; the bounds check catches them on its own.
    h = hourly("shimla")
    assert not indoor.applicability(h[24:48], False)["ok"]
    preds = indoor.predict(h, 24, "rcc_brick_top", False, False, hours=len(h))
    assert len(indoor.physics_check(h, preds, "rcc_brick_top", False)) > len(preds) // 2


def test_impossible_hours_are_caught():
    h = hourly("delhi_2024-05-28")
    p = indoor.predict(h, 40, "rcc_brick_top", True, False, hours=3)
    hot = [{**p[0], "indoor": max(r["t"] for r in h[16:41]) + 15}]
    cold = [{**p[1], "indoor": min(r["t"] for r in h[17:42]) - 15}]
    assert indoor.physics_check(h, hot, "rcc_brick_top", False) == [hot[0]["time"]]
    assert indoor.physics_check(h, cold, "rcc_brick_top", False) == [cold[0]["time"]]


def test_a_cooler_may_go_below_air_but_not_below_wet_bulb():
    h = hourly("delhi_2024-05-28")
    p = indoor.predict(h, 40, "rcc_brick_top", True, True, hours=1)[0]
    past = h[16:41]
    air_min, twb_min = min(r["t"] for r in past), min(r["twb"] for r in past)
    between = [{**p, "indoor": (air_min - 6 + twb_min) / 2}] if air_min - 6 > twb_min else []
    if between:
        assert indoor.physics_check(h, between, "rcc_brick_top", True) == []
        assert indoor.physics_check(h, between, "rcc_brick_top", False) == [p["time"]]


def test_api_falls_back_to_roof_offsets_when_the_model_is_impossible(monkeypatch):
    real = indoor.predict
    monkeypatch.setattr(indoor, "predict", lambda *a, **k: [{**x, "indoor": x["indoor"] + 30, "low": x["low"] + 30, "high": x["high"] + 30} for x in real(*a, **k)])
    r = status(fake_forecast(36, 27, 20, 35), roof="rcc_brick_top", devices={"fan": True}, lat=28.61, lon=77.21)
    assert r["indoor"]["basis"] == "offset" and r["indoor"]["applicability"]["physics_violations"] > 0
