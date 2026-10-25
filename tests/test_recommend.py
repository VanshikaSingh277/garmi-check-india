"""Fix recommendations against the real catalogue (apps/api/data/fixes.json). Ported from reference/thandak_v2's tests.
Where the reference and the current rules disagree, the current rules win and the test says so.
Run from the repo root:  python tests/test_recommend.py"""
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import solutions as S  # noqa: E402
from engine import verified as V  # noqa: E402

JAIPUR = {"climate": "semi_arid",
          "causes": {"dark_roofs": 1.2, "bare_paved_ground": 0.9, "low_tree_cover": 0.5, "night_heat": 1.3}}
NO_PROFILE = {"climate": "semi_arid"}
HIGH_DRY = {"heat_level": "high", "afternoon_rh_pct": 24, "afternoon_twb_c": 20}
TIN_FAMILY = {"roof_type": "tin", "top_floor": True, "vulnerable": True, "devices": ["fan", "cooler"], "roof_access": True,
              "cross_ventilation": False, "outdoor_worker": False, "has_open_ground": False, "budget": "medium"}
CONCRETE_FAMILY = {**TIN_FAMILY, "roof_type": "concrete"}


@contextmanager
def threshold_verified(key="evaporative.max_twb"):
    """Treat one threshold as verified, to test the logic behind a feature that stays off until the team verifies it."""
    orig = V.rule_ok
    V.rule_ok = lambda k: True if k == key else orig(k)
    try:
        yield
    finally:
        V.rule_ok = orig


def run(category="family", place=JAIPUR, household=None, weather=HIGH_DRY, lang="en"):
    return S.recommend(category, place, household, weather, lang)


def ids(out, tier=None):
    tiers = [tier] if tier else out["fixes"].keys()
    return [f["id"] for t in tiers for f in out["fixes"][t]]


def excluded(out):
    return {e["id"]: e["reason"]["code"] for e in out["excluded"]}


def signature(out):
    return (tuple(ids(out)), tuple(sorted(excluded(out))), out.get("fan_profile"))


# ---- family advice does not need satellite data
def test_no_satellite_profile_still_gives_full_advice():
    out = run(place=NO_PROFILE, household=CONCRETE_FAMILY)
    assert "night_ventilation" in ids(out, "today")
    assert "fam_vulnerable_care" in ids(out, "today")
    assert "lime_whitewash" in ids(out, "quick")
    assert "cool_roof_coating" in ids(out, "moderate")
    assert not out["inputs"]["has_area_profile"]


def test_area_cooler_than_city_average_changes_nothing():
    cooler_area = {"climate": "semi_arid", "causes": {"dark_roofs": -0.4, "low_tree_cover": -0.8}}
    assert signature(run(place=cooler_area, household=TIN_FAMILY)) == signature(run(place=NO_PROFILE, household=TIN_FAMILY))


def test_tin_top_floor_gets_roof_fixes_without_a_roof_cause():
    area = {"climate": "semi_arid", "causes": {"low_tree_cover": 0.6, "bare_paved_ground": 0.9}}
    out = run(place=area, household={**TIN_FAMILY, "budget": "high"})
    for fid in ("cool_roof_coating", "modroof"):
        assert fid in ids(out), fid
    # current rule wins over the reference: lime is not for tin sheets (they need a metal paint), so it is left out with a reason
    assert excluded(out).get("lime_whitewash") == "roof_mismatch"


def test_area_causes_never_trigger_family_fixes():
    out = run(place=JAIPUR, household={})
    for fid in ("lime_whitewash", "cool_roof_coating", "modroof", "fam_roof_insulation"):
        assert fid not in ids(out), fid


def test_area_causes_add_because_lines():
    window = next(f for f in run(household=TIN_FAMILY)["fixes"]["today"] if f["id"] == "night_ventilation")
    codes = [r["code"] for r in window["because"]]
    assert codes[0] == "always"
    assert "area_cause" in codes


# ---- every answer matters
BASE = {"roof_type": "concrete", "top_floor": False, "vulnerable": False, "devices": [], "roof_access": True,
        "cross_ventilation": True, "outdoor_worker": False, "has_open_ground": False, "budget": "high"}


def test_each_household_answer_changes_the_output():
    b = BASE
    pairs = {
        "vulnerable": (b, {**b, "vulnerable": True}),
        "devices: fan": (b, {**b, "devices": ["fan"]}),
        "devices: cooler": (b, {**b, "devices": ["cooler"]}),
        "cross_ventilation": ({**b, "devices": ["fan"]}, {**b, "devices": ["fan"], "cross_ventilation": False}),
        "outdoor_worker": (b, {**b, "outdoor_worker": True}),
        "top_floor": (b, {**b, "top_floor": True}),
        "roof_type": ({**b, "top_floor": True}, {**b, "top_floor": True, "roof_type": "tin"}),
        "budget": ({**b, "top_floor": True}, {**b, "top_floor": True, "budget": "low"}),
        "roof_access": ({**b, "top_floor": True}, {**b, "top_floor": True, "roof_access": False}),
        "has_open_ground": (b, {**b, "has_open_ground": True}),
    }
    for name, (before, after) in pairs.items():
        assert signature(run(place=NO_PROFILE, household=before)) != signature(run(place=NO_PROFILE, household=after)), name


def test_vulnerable_adds_content_not_just_score():
    on = run(household={**TIN_FAMILY, "vulnerable": True})
    off = run(household={**TIN_FAMILY, "vulnerable": False})
    assert "fam_vulnerable_care" in ids(on, "today")
    assert "fam_vulnerable_care" not in ids(off, "today")
    assert (on["fan_profile"], off["fan_profile"]) == ("vulnerable", "standard")


def test_stone_slab_and_asbestos_get_roof_fixes():
    for roof in ("stone_slab", "Stone slab", "patti", "asbestos"):
        out = run(household={**TIN_FAMILY, "roof_type": roof})
        assert "lime_whitewash" in ids(out), roof
        assert "cool_roof_coating" in ids(out), roof
        assert out["warnings"] == [], roof


def test_no_roof_access_leaves_roof_fixes_out_with_reason():
    out = run(household={**CONCRETE_FAMILY, "roof_access": False})
    assert excluded(out).get("cool_roof_coating") == "no_roof_access"
    assert excluded(out).get("lime_whitewash") == "no_roof_access"


# ---- real-time inputs
def _forecast():
    times, rh = [], []
    for day, afternoon in (("2026-05-20", 22), ("2026-05-21", 40)):
        for h in range(24):
            times.append(f"{day}T{h:02d}:00")
            rh.append(afternoon if 12 <= h < 17 else 68)
    return times, rh


def test_afternoon_humidity_does_not_depend_on_the_hour_opened():
    times, rh = _forecast()
    assert S.afternoon_rh(times, rh, datetime(2026, 5, 20, 6, 0)) == 22
    assert S.afternoon_rh(times, rh, datetime(2026, 5, 20, 15, 0)) == 22
    assert S.afternoon_rh(times, rh, datetime(2026, 5, 20, 19, 0)) == 40


def test_afternoon_humidity_none_when_forecast_is_short():
    times, rh = _forecast()
    assert S.afternoon_rh(times[:13], rh[:13], datetime(2026, 5, 20, 6, 0)) is None


def test_evaporative_cards_off_until_threshold_verified():
    out = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 24, "afternoon_twb_c": 20})
    assert not {"fam_cooler_dry", "fam_cooler_humid", "fam_wet_screen"} & set(ids(out))
    left = [e for e in out["excluded"] if e["id"] in ("fam_cooler_dry", "fam_cooler_humid", "fam_wet_screen")]
    assert {e["reason"]["code"] for e in left} == {"threshold_not_verified"}
    assert len([e for e in left if e["id"].startswith("fam_cooler")]) == 1     # the cooler pair is listed once


@threshold_verified()
def test_khus_screen_follows_afternoon_wet_bulb():
    dry = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 24, "afternoon_twb_c": 20})
    humid = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 65, "afternoon_twb_c": 28})
    assert "fam_wet_screen" in ids(dry, "quick")
    assert excluded(humid).get("fam_wet_screen") == "too_humid"


@threshold_verified()
def test_unknown_humidity_leaves_evaporative_fixes_out_with_reason():
    out = run(household=TIN_FAMILY, weather={"heat_level": "high"})
    assert excluded(out).get("fam_wet_screen") == "humidity_unknown"
    assert "fam_cooler_dry" not in ids(out) and "fam_cooler_humid" not in ids(out)


@threshold_verified()
def test_cooler_advice_switches_with_wet_bulb():
    dry = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 30, "afternoon_twb_c": 21})
    humid = run(place={"climate": "humid"}, household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 75, "afternoon_twb_c": 29})
    assert "fam_cooler_dry" in ids(dry, "today")
    assert "fam_cooler_humid" in ids(humid, "today")
    for out in (dry, humid):  # the other variant is not listed as "left out"
        assert not ({"fam_cooler_dry", "fam_cooler_humid"} & set(excluded(out)))


def test_colony_checkins_follow_heat_level():
    place = {"climate": "semi_arid", "causes": {"dark_roofs": 0.8, "night_heat": 0.7}}
    assert "col_buddy_checks" in ids(run("colony", place, weather=HIGH_DRY), "today")
    assert "col_buddy_checks" not in ids(run("colony", place, weather={"heat_level": "low", "afternoon_rh_pct": 24, "afternoon_twb_c": 20}))


def test_colony_without_satellite_profile_still_gets_common_fixes():
    out = run("colony", NO_PROFILE, weather=HIGH_DRY)
    assert "col_bulk_cool_roofs" in ids(out)
    roofs = next(f for t in out["fixes"].values() for f in t if f["id"] == "col_bulk_cool_roofs")
    assert roofs["because"][0]["code"] == "no_area_profile"


def test_no_forecast_still_gives_household_advice():
    out = run(household=CONCRETE_FAMILY, weather=None)
    assert "night_ventilation" in ids(out)
    assert "lime_whitewash" in ids(out)
    assert "fam_vulnerable_care" not in ids(out)


# ---- ranking and exclusions
def test_today_order_is_safety_then_core_then_advice():
    out = run(household={**TIN_FAMILY, "outdoor_worker": True})
    assert ids(out, "today") == ["fam_vulnerable_care", "fam_outdoor_work", "fam_fan_limits",
                                 "night_ventilation", "fam_night_fan_pull"]


def test_measured_fix_ranks_above_unmeasured():
    # reference used a tin roof; lime is not for tin here, so the same rule is checked on a concrete roof
    assert ids(run(household=CONCRETE_FAMILY), "quick")[0] == "lime_whitewash"


def test_review_numbers_are_not_shown_as_a_range():
    trees = next(f for f in run("colony")["fixes"]["long"] if f["id"] == "col_trees_dense_native")
    assert trees["effect"]["kind"] == "global_only"
    assert trees["effect"]["max_c"] is None
    assert "9" not in trees["effect"]["text"]


def test_effect_numbers_come_from_verified_numbers():
    from engine import verified as V
    roof = next(f for f in run(household=CONCRETE_FAMILY)["fixes"]["moderate"] if f["id"] == "cool_roof_coating")
    v = V.value("coolroof.indoor_drop")
    assert (roof["effect"]["min_c"], roof["effect"]["max_c"]) == (v["india_low"], v["india_high"])


def test_low_budget_lists_left_out_fixes_with_subsidy_hint():
    left = {e["id"]: e["reason"] for e in run(household={**CONCRETE_FAMILY, "budget": "low"})["excluded"]}
    assert left["cool_roof_coating"]["code"] == "over_budget"
    assert left["cool_roof_coating"]["subsidy_possible"]
    assert "subsid" in left["cool_roof_coating"]["text"]
    assert not left["fam_roof_insulation"]["subsidy_possible"]


def test_unsourced_fixes_are_labelled_general_advice():
    out = run(household=TIN_FAMILY)
    screen = next(f for f in out["fixes"]["today"] if f["id"] == "fam_night_fan_pull")
    assert screen["effect"]["kind"] == "general" and screen["effect"]["min_c"] is None


# ---- input safety
@threshold_verified()
def test_messy_inputs_are_normalised():
    out = run(household={**CONCRETE_FAMILY, "budget": "Low", "devices": "Desert cooler"},
              weather={"heat_level": "HIGH", "afternoon_rh_pct": 24, "afternoon_twb_c": 20})
    assert out["warnings"] == []
    assert "fam_cooler_dry" in ids(out, "today")
    assert "cool_roof_coating" in excluded(out)
    assert run(household={**TIN_FAMILY, "budget": 4000})["excluded"] == run(household={**TIN_FAMILY, "budget": "low"})["excluded"]


def test_bad_inputs_warn_but_never_blank_safety_advice():
    out = run(household={**TIN_FAMILY, "budget": "under_5000", "roof_type": "mansion", "vulnerable": "yes"},
              weather={"heat_level": "high", "afternoon_rh_pct": 150, "afternoon_twb_c": 99})
    assert len(out["warnings"]) == 5
    assert "night_ventilation" in ids(out)
    assert "fam_fan_limits" in ids(out)


def test_wrong_category_is_a_programming_error():
    try:
        run(category="families")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_output_is_json_ready():
    json.dumps(run(household=TIN_FAMILY, lang="hi"), ensure_ascii=False)


# ---- Hindi
def test_hindi_mode_has_no_english():
    out = run(household={**TIN_FAMILY, "outdoor_worker": True}, lang="hi")
    assert out["needs_translation"] == []
    for t in out["fixes"].values():
        for f in t:
            texts = [f["title"], f["effect"]["text"], *f["steps"], *(r["text"] for r in f["because"])]
            for x in texts:
                assert any("ऀ" <= ch <= "ॿ" for ch in x), (f["id"], x)
    for e in out["excluded"]:
        assert any("ऀ" <= ch <= "ॿ" for ch in e["reason"]["text"]), e


# ---- before / after readings
def test_corrects_for_a_hotter_week():
    before = [{"indoor_c": i, "outdoor_c": o} for i, o in zip([39.0, 39.4, 38.8, 39.2, 39.1], [40.0, 40.3, 39.9, 40.2, 40.1])]
    after = [{"indoor_c": i, "outdoor_c": o} for i, o in zip([39.5, 39.7, 39.3, 39.6, 39.4], [43.0, 43.1, 42.9, 43.2, 42.8])]
    naive = sum(r["indoor_c"] for r in before) / 5 - sum(r["indoor_c"] for r in after) / 5
    res = S.estimate_fix_effect(before, after)
    assert naive < 0                 # indoor alone says the fix "failed"
    assert res["status"] == "ok"
    assert abs(res["effect_c"] - 2.5) < 1e-9
    assert res["range_c"][0] < 2.5


def test_range_never_narrower_than_half_a_degree():
    b, a = {"indoor_c": 38.0, "outdoor_c": 41.0}, {"indoor_c": 37.0, "outdoor_c": 41.0}
    assert S.estimate_fix_effect([b] * 4, [a] * 4)["range_c"] == [0.5, 1.5]


def test_needs_three_days_each_side():
    r = {"indoor_c": 38.0, "outdoor_c": 41.0}
    assert S.estimate_fix_effect([r, r], [r, r, r])["status"] == "need_more_readings"


# ---- catalogue
def test_catalogue_has_no_errors():
    assert S.validate_rules()["errors"] == []


def test_climate_from_district_dryness():
    assert S.climate_of({"tmax_mean_c": 37.6, "twb_max_mean_c": 21.4}) == "arid"        # Jaipur
    assert S.climate_of({"tmax_mean_c": 37.7, "twb_max_mean_c": 22.8}) == "semi_arid"   # New Delhi
    assert S.climate_of({"tmax_mean_c": 34.3, "twb_max_mean_c": 27.5}) == "humid"       # Chennai
    assert S.climate_of(None) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
