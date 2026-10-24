"""/api/status/individual end to end, with a fixed synthetic forecast instead of the live one.
Run from the repo root:  python tests/test_api_fixes.py"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
import main  # noqa: E402
from engine import normals, weather  # noqa: E402
from engine.heat import heat_index_c, wet_bulb_c  # noqa: E402


def fake_forecast(day_max, night_min, afternoon_rh, night_rh):
    """Past 24 h + next 48 h, hottest at 15:00, with the given humidity in the afternoon (12-17) and at night."""
    start = main._now_dt().replace(minute=0, second=0, microsecond=0) - timedelta(hours=24)
    rows = []
    for k in range(72):
        ts = start + timedelta(hours=k)
        h = ts.hour
        frac = max(0.0, 1 - abs(h - 15) / 9)          # 0 at night, 1 at 15:00
        t = round(night_min + (day_max - night_min) * frac, 1)
        rh = afternoon_rh if 12 <= h < 17 else night_rh
        rows.append({"time": ts.strftime("%Y-%m-%dT%H:00"), "t": t, "rh": rh, "sw": 800 * frac, "ws": 2.0,
                     "hi": round(heat_index_c(t, rh), 1), "twb": round(wet_bulb_c(t, rh), 1)})
    return {"hourly": rows, "fetched_at": start.isoformat(), "source": "test"}


def status(forecast, normal=38.0, **answers):
    """normal: the day's 1991-2020 normal maximum, fixed so the IMD departure rule doesn't depend on today's date."""
    weather.fetch = lambda lat, lon: forecast
    main.normals.normal_tmax = lambda *a, **k: normal
    q = main.IndividualIn(**answers)
    return main.status_individual(q)


def ids(fixes, tier=None):
    return [f["id"] for t, lst in fixes["fixes"].items() if tier in (None, t) for f in lst]


def test_jaipur_tin_roof_family_on_a_high_day():
    r = status(fake_forecast(43, 29, 18, 35), lat=26.91, lon=75.79, roof="tin_top", vulnerable=["elderly"],
               devices={"fan": True, "cooler": True}, roof_access=True, cross_ventilation=False, budget="medium")
    fx = r["fixes"]
    assert r["risk"]["level"] in ("high", "extreme"), r["risk"]
    assert fx["inputs"]["heat_level"] == r["risk"]["level"]          # heat level comes from the existing rules
    assert fx["inputs"]["climate"] == "arid"
    assert 15 <= fx["inputs"]["afternoon_rh_pct"] <= 20
    today = ids(fx, "today")
    for fid in ("fam_vulnerable_care", "fam_fan_limits", "night_ventilation", "fam_cooler_dry", "fam_night_fan_pull"):
        assert fid in today, (fid, today)
    assert today[0] == "fam_vulnerable_care"
    assert "cool_roof_coating" in ids(fx)
    left = {e["id"]: e["reason"]["code"] for e in fx["excluded"]}
    assert left.get("lime_whitewash") == "roof_mismatch"
    assert left.get("modroof") == "over_budget"
    assert fx["fan_profile"] == "vulnerable" and r["fan"]["group"] == "older"  # stricter fan limits in the hourly plan
    assert r["risk"]["home"] == ["tin_roof_top_floor", "vulnerable_person"]       # beside the level, not added to it


def test_outdoor_worker_gets_adult_fan_limits_and_work_advice():
    r = status(fake_forecast(43, 29, 18, 35), lat=26.91, lon=75.79, roof="rcc_brick_top", vulnerable=["outdoor_worker"],
               devices={"fan": True}, roof_access=True)
    assert r["fan"]["group"] == "adult"
    assert "vulnerable_person" not in r["risk"]["home"]
    assert "fam_outdoor_work" in ids(r["fixes"], "today")


def test_village_with_no_satellite_profile_gets_full_family_advice():
    r = status(fake_forecast(41, 27, 25, 45), lat=25.5, lon=73.2, roof="rcc_brick_top", vulnerable=[],
               devices={"fan": True}, roof_access=True)
    fx = r["fixes"]
    assert not fx["inputs"]["has_area_profile"]
    assert "night_ventilation" in ids(fx, "today")
    assert "lime_whitewash" in ids(fx, "quick")
    assert "cool_roof_coating" in ids(fx, "moderate")
    assert fx["warnings"] == []


def test_humid_city_with_a_cooler_at_75_percent_afternoon_humidity():
    r = status(fake_forecast(35, 28, 75, 85), lat=13.08, lon=80.27, roof="lower_floor", vulnerable=[],
               devices={"fan": True, "cooler": True}, roof_access=False)
    fx = r["fixes"]
    assert fx["inputs"]["climate"] == "humid"
    assert fx["inputs"]["afternoon_rh_pct"] == 75
    if fx["inputs"]["heat_level"] != "low":                           # cooler advice needs at least a Moderate day
        assert "fam_cooler_humid" in ids(fx, "today")
        assert "fam_cooler_dry" not in ids(fx)
    assert "cool_roof_coating" not in ids(fx)                          # a floor above: no roof fixes
    left = {e["id"]: e["reason"]["code"] for e in fx["excluded"]}
    assert "fam_cooler_dry" not in left


def test_hindi_response_has_no_english_fixes():
    r = status(fake_forecast(43, 29, 18, 35), lat=26.91, lon=75.79, roof="asbestos_top", vulnerable=["child"],
               devices={"fan": True}, roof_access=True, budget=3000, lang="hi")
    assert r["fixes"]["needs_translation"] == []
    assert r["indoor"]["roof_proxy"] == "tin_top"
    assert "lime_whitewash" in ids(r["fixes"])                         # lime is fine on asbestos-cement sheets


def test_bad_answers_never_crash_the_endpoint():
    r = status(fake_forecast(43, 29, 18, 35), lat=26.91, lon=75.79, roof="tin_top", budget="HIGH-ish")
    assert "night_ventilation" in ids(r["fixes"])
    assert r["fixes"]["warnings"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
