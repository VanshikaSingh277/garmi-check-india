"""Room estimate rules (BACKEND_SPEC §7.4, §2 rule 4): offset fallback outside the model's training range, numbers only
in Delhi under ROOM_MODEL_MODE=validated_only, fan states from the cautious (high) end of the range."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import indoor, plan, verified as V  # noqa: E402
from tests.test_api_fixes import fake_forecast, status  # noqa: E402

DELHI = dict(lat=28.61, lon=77.21)
JAIPUR = dict(lat=26.91, lon=75.79)


def test_offset_estimate_uses_measured_roof_offsets():
    rows = [{"time": f"2026-05-20T{h:02d}:00", "t": 40.0, "rh": 20} for h in range(24)]
    est = {h["time"][11:13]: h for h in indoor.offset_estimate(rows, "rcc_brick_top")}
    o = V.value("roof.offset.rcc_top")
    assert est["15"]["low"] == round(40 + o["afternoon_iqr"][0], 1) and est["15"]["high"] == round(40 + o["afternoon_iqr"][1], 1)
    assert est["03"]["high"] == round(40 + o["night_iqr"][1], 1)
    wide = est["10"]["high"] - est["10"]["low"]
    assert wide >= est["15"]["high"] - est["15"]["low"] and wide >= est["03"]["high"] - est["03"]["low"]


def test_hot_day_outside_training_range_uses_offset_in_delhi():
    r = status(fake_forecast(46, 33, 15, 30), roof="rcc_brick_top", devices={"fan": True}, **DELHI)
    assert r["indoor"]["basis"] == "offset" and r["indoor"]["numbers_shown"] is True and r["indoor"]["next24"]
    assert r["plan"]["estimate"] == "offset" and (r["plan"]["open"] or r["plan"]["close"])


def test_numbers_hidden_outside_delhi_but_plan_still_works():
    r = status(fake_forecast(40, 27, 20, 35), roof="tin_top", devices={"fan": True}, **JAIPUR)
    assert r["indoor"]["numbers_shown"] is False and r["indoor"]["next24"] == [] and r["indoor"]["peak"] is None
    assert all(h["indoor"] is None and h["low"] is None and h["high"] is None for h in r["plan"]["hours"])
    assert any(h["window"] for h in r["plan"]["hours"]) and r["fan"]["basis"] == "indoor"


def test_fan_state_uses_the_high_end_of_the_room_range():
    hours = [{"time": "2026-05-20T15:00", "indoor": 34.0, "low": 32.0, "high": 36.0}]
    out = plan.build(hours, [{"time": "2026-05-20T15:00", "t": 40.0, "hi": 41.0}], {"not_enough_from": 35.0, "avoid_from": 38.0})
    assert out["hours"][0]["fan"] == "fan_not_enough_alone"    # the middle (34) would have said "fan helps"
