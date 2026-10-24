"""Golden cases and safety properties from the external review (2026-10-24): the heat level must follow IMD's rules
(heatwave by actual temperature and by departure from normal, plains / hill / coastal), dry heat must not read mild,
household answers never change the level, and the fix list must carry the safety cautions.
Run from the repo root:  python tests/test_heat_level.py"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import normals, rules, solutions  # noqa: E402
from engine.heat import heat_index_c, wet_bulb_c  # noqa: E402


def rows(t, rh, n=24):
    return [{"time": f"2026-05-20T{h:02d}:00", "t": t, "rh": rh, "hi": heat_index_c(t, rh), "twb": wet_bulb_c(t, rh)} for h in range(n)]


def level(t, rh, normal=None, station="plains", in_delhi=False, uncertain=False):
    r = rows(t, rh)
    return rules.risk(r, r, r, in_delhi=in_delhi, days=[{"day": "today", "tmax": t, "normal": normal, "uncertain": uncertain}], station=station)


def codes(r):
    return [x["code"] for x in r["reasons"]]


# ---- the review's cases
def test_a_jaipur_44_dry():
    r = level(44, 10, normal=38.5)                      # April: 5.5 C above normal -> IMD heatwave
    assert r["level"] == "high" and "heatwave_departure" in codes(r), r
    r = level(44, 10, normal=40.5)                      # May: 3.5 above normal -> no heatwave
    assert r["level"] == "moderate", r
    r = level(46, 10, normal=43.0)                      # feels-like 42 (yellow) but the air is 46 (orange)
    assert r["level"] == "high" and "base_air_temp" in codes(r), r


def test_b_chennai_36_humid_is_extreme_from_wet_bulb():
    r = level(36, 75, normal=37.0, station="coastal")
    assert r["level"] == "extreme" and "wet_bulb_critical" in codes(r), r


def test_c_shimla_32_hill_heatwave():
    assert level(32, 40, normal=24.5, station="hill")["level"] == "extreme"      # 7.5 above normal: severe
    assert level(32, 40, normal=24.5, station="hill", uncertain=True)["level"] == "high"   # uncertain normal: one level at most
    assert level(32, 40, normal=27.0, station="hill")["level"] == "high"         # 5 above normal
    assert level(32, 40, normal=27.0, station="plains")["level"] == "low"       # plains need 40 C first
    r = level(32, 40, normal=None, station="hill")                              # no normal: no crash, no departure rule
    assert r["level"] == "low", r


def test_d_household_never_changes_the_level():
    r = level(38, 30)
    assert r["level"] == "moderate"
    assert rules.home_factors("tin_top", ["elderly"], {"fan": False}) == ["tin_roof_top_floor", "vulnerable_person", "no_cooling"]


def test_47_dry_is_severe_heatwave():
    r = level(47, 8)
    assert r["level"] == "extreme" and "severe_heatwave_tmax" in codes(r), r


def test_coastal_and_plains_entry_values():
    assert level(37, 40, normal=32.5, station="coastal")["level"] == "high"     # coast: >=37 and +4.5
    assert level(37, 40, normal=32.0, station="plains")["level_index"] < 2      # plains: 37 is below the 40 entry
    assert level(30, 40, normal=25.5, station="hill")["level"] == "high"        # hill: >=30 and +4.5


# ---- properties
def test_hotter_never_lowers_the_level():
    for rh in range(10, 95, 10):
        prev = -1
        for t in range(28, 49):
            lv = level(t, rh, normal=36.0)["level_index"]
            assert lv >= prev, (t, rh)
            prev = lv


def test_dry_air_at_40_plus_never_reads_below_the_air_band():
    for t in range(40, 49):
        for rh in range(5, 60, 5):
            assert level(t, rh)["level_index"] >= rules.base_from_heat_index(t), (t, rh)


# ---- normals and station type
def test_normals_are_plausible_where_available():
    if not normals.available():
        return
    from engine import districts
    for (lat, lon), lo, hi in (((28.61, 77.21), 37.0, 42.5), ((31.10, 77.17), 18.0, 30.0)):
        d = districts.district_at(lat, lon)
        v = normals.normal_tmax(d["id"], date(2026, 5, 15))
        assert lo <= v <= hi, (d["district"], v)


def test_station_type():
    assert normals.station_type(31.10, 77.17, 2100) == "hill"
    assert normals.station_type(28.61, 77.21, 215) == "plains"
    if normals._coast() is not None:
        assert normals.station_type(13.08, 80.27, 10) == "coastal"


# ---- the fix list's safety cautions
FAMILY = {"roof_type": "asbestos", "top_floor": True, "roof_access": True, "vulnerable": True, "devices": ["fan"], "budget": "high"}


def all_fixes(out):
    return [f for t in out["fixes"].values() for f in t]


def test_asbestos_fixes_carry_the_warning():
    out = solutions.recommend("family", {"climate": "semi_arid"}, FAMILY, {"heat_level": "high", "afternoon_twb_c": 20})
    for f in all_fixes(out):
        if f["id"] in ("lime_whitewash", "cool_roof_coating"):
            assert "Asbestos" in (f["caution"] or ""), f["id"]
    concrete = solutions.recommend("family", {"climate": "semi_arid"}, {**FAMILY, "roof_type": "concrete"}, {"heat_level": "high"})
    for f in all_fixes(concrete):
        assert "Asbestos" not in (f["caution"] or ""), f["id"]


def test_no_plain_give_water_line_for_babies():
    out = solutions.recommend("family", {"climate": "semi_arid"}, FAMILY, {"heat_level": "high", "afternoon_twb_c": 20})
    care = next(f for f in all_fixes(out) if f["id"] == "fam_vulnerable_care")
    text = " ".join(care["steps"])
    assert "keep giving water" not in text and "Breastfeed" in text
    hyd = next(f for f in all_fixes(out) if f["id"] == "hydrate_shade")
    assert "breastfeed" in hyd["caution"]


def test_thermocol_fire_warning():
    out = solutions.recommend("family", {"climate": "semi_arid"}, FAMILY, {"heat_level": "high"})
    ins = next(f for f in all_fixes(out) if f["id"] == "fam_roof_insulation")
    assert "thermocol" in ins["caution"]


def test_unknown_climate_never_shows_both_tree_variants():
    out = solutions.recommend("colony", {}, None, {"heat_level": "high"})
    shown = {f["id"] for f in all_fixes(out)}
    assert not {"col_trees_dense_native", "col_trees_sparse_ventilated"} & shown
    left = {e["id"]: e["reason"]["code"] for e in out["excluded"]}
    assert left.get("col_trees_dense_native") == "climate_unknown"


def test_cooler_is_never_called_good_at_a_dangerous_wet_bulb():
    hh = {"devices": ["cooler"], "top_floor": False}
    out = solutions.recommend("family", {"climate": "semi_arid"}, hh, {"heat_level": "high", "afternoon_rh_pct": 45, "afternoon_twb_c": 31.4})
    ids = {f["id"] for f in all_fixes(out)}
    assert "fam_cooler_dry" not in ids and "fam_cooler_humid" in ids


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
