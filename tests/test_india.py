"""India-wide checks: place naming, PIN/place search, Delhi-only rule, indoor-model applicability.
Run from heat-india/:  python tests/test_india.py   (needs the gazetteer files built by pipelines/places/build_gazetteer.py)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import indoor, places, rules  # noqa: E402
from test_rules import rows  # noqa: E402


def test_points_are_named_with_the_right_state():
    cases = {(26.9124, 75.7873): ("Rajasthan", "Jaipur"), (12.9352, 77.6245): ("Karnataka", "Bengaluru"),
             (22.5530, 88.3520): ("West Bengal", "Kolkata"), (34.1526, 77.5771): ("Ladakh", "Leh"),
             (11.6234, 92.7265): ("Andaman and Nicobar", "Port Blair"), (28.6315, 77.2167): ("Delhi", "Delhi")}
    for (lat, lon), (state, town) in cases.items():
        d = places.describe(lat, lon)
        assert d["in_india"] and d["state"] == state, (lat, lon, d)
        assert town in (d["label"] or ""), (lat, lon, d)


def test_points_outside_india_are_rejected():
    for lat, lon in [(27.7172, 85.3240), (15.0, 68.5), (23.8103, 90.4125)]:  # Kathmandu, Arabian Sea, Dhaka
        assert places.describe(lat, lon)["in_india"] is False, (lat, lon)


def test_pin_and_name_search():
    r = places.search("302017")
    assert r and r[0]["kind"] == "pin" and "Jaipur" in r[0]["sub"], r
    assert 26.7 < r[0]["lat"] < 27.0 and 75.7 < r[0]["lon"] < 75.95, r[0]
    leh = places.search("194101")[0]
    assert abs(leh["lat"] - 34.16) < 0.1 and abs(leh["lon"] - 77.58) < 0.1, leh  # GeoNames' estimate was ~170 km off
    assert places.search("Bangalore")[0]["label"] == "Bengaluru"
    assert places.search("गुरुग्राम")[0]["label"] == "Gurugram"
    assert places.search("x") == []


def test_delhi_p97_rule_only_applies_in_delhi():
    # two days with daily mean ~36 C (> Delhi HAP p97 35.3) but heat index below the orange band
    hot = rows(36, 25)
    in_delhi = rules.risk(hot, hot, hot, "rcc_brick_top", [], {"ac": True}, indoor_peak=30.0, in_delhi=True)
    elsewhere = rules.risk(hot, hot, hot, "rcc_brick_top", [], {"ac": True}, indoor_peak=30.0, in_delhi=False)
    assert any(r["code"] == "heatwave_p97" for r in in_delhi["reasons"]), in_delhi
    assert not any(r["code"] == "heatwave_p97" for r in elsewhere["reasons"]), elsewhere


def test_indoor_model_refuses_conditions_it_never_saw():
    assert indoor.applicability(rows(32, 40), in_delhi=True)["ok"]
    assert not indoor.applicability(rows(15, 60), in_delhi=False)["ok"]   # cold night / hills
    assert not indoor.applicability(rows(30, 95), in_delhi=False)["ok"]   # saturated monsoon air
    fit = indoor.applicability(rows(32, 40), in_delhi=False)
    assert fit["ok"] and fit["validated_here"] is False


def test_window_plan_uses_the_model_range_only():
    from engine import plan
    lim = rules.fan_limits("older")
    ind = [{"time": f"2026-05-20T{h:02d}:00", "indoor": 32.0, "low": 30.0, "high": 34.0} for h in range(4)]
    out = [{"time": f"2026-05-20T{h:02d}:00", "t": t, "hi": t} for h, t in enumerate([28.0, 31.0, 36.0, 29.5])]
    p = plan.build(ind, out, lim)
    assert [h["window"] for h in p["hours"]] == ["open", "either", "close", "open"], p
    assert p["open"] == [["00:00", "01:00"], ["03:00", "04:00"]] and p["close"] == [["02:00", "03:00"]], p
    assert plan.build([], out, lim)["hours"][0]["window"] is None  # no indoor estimate -> no window advice


def test_fixes_explain_why_and_what_was_hidden():
    from engine import solutions
    r = solutions.pick("individual", "tin_top", False, "en")
    assert {x["id"]: x["reason"] for x in r["skipped"]}["cool_roof_coating"] == "no_roof_access"
    r = solutions.pick("individual", "rcc_brick_top", True, "en")
    assert [x["id"] for x in r["cooling"]] == ["lime_whitewash", "cool_roof_coating"]  # cheapest first
    assert "roof:rcc_brick_top" in r["cooling"][0]["why"] and "roof_access" in r["cooling"][0]["why"]
    assert {x["id"]: x["reason"] for x in r["skipped"]}["modroof"] == "roof_mismatch"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == "__main__":
            fn()
            print("PASS", name)
