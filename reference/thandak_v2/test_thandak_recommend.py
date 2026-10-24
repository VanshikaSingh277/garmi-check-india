"""Tests for the Thandak v2 engine. Standard library only: python -m unittest -v"""
import json
import unittest
from datetime import datetime

from thandak_recommend import (afternoon_rh, estimate_fix_effect, load_rules, recommend,
                               validate_rules)

RULES = load_rules()
JAIPUR = {"climate": "semi_arid",
          "causes": {"dark_roofs": 1.2, "bare_paved_ground": 0.9, "low_tree_cover": 0.5, "night_heat": 1.3}}
NO_PROFILE = {"climate": "semi_arid"}
HIGH_DRY = {"heat_level": "high", "afternoon_rh_pct": 24}
TIN_FAMILY = {"roof_type": "tin", "top_floor": True, "vulnerable": True, "devices": ["fan", "cooler"],
              "cross_ventilation": False, "outdoor_worker": False, "has_open_ground": False, "budget": "medium"}


def run(category="family", place=JAIPUR, household=None, weather=HIGH_DRY, lang="en"):
    return recommend(category, place, household, weather, RULES, lang)


def ids(out, tier=None):
    tiers = [tier] if tier else out["fixes"].keys()
    return [f["id"] for t in tiers for f in out["fixes"][t]]


def excluded(out):
    return {e["id"]: e["reason"]["code"] for e in out["excluded"]}


def signature(out):
    return (tuple(ids(out)), tuple(sorted(excluded(out))), out.get("fan_profile"))


class FamilyAdviceDoesNotNeedSatelliteData(unittest.TestCase):
    def test_no_satellite_profile_still_gives_full_advice(self):
        out = run(place=NO_PROFILE, household=TIN_FAMILY)
        self.assertIn("fam_window_timing", ids(out, "today"))
        self.assertIn("fam_vulnerable_care", ids(out, "today"))
        self.assertIn("fam_roof_whitewash", ids(out, "quick"))
        self.assertIn("fam_cool_roof_coating", ids(out, "moderate"))
        self.assertFalse(out["inputs"]["has_area_profile"])

    def test_area_cooler_than_city_average_changes_nothing(self):
        cooler_area = {"climate": "semi_arid", "causes": {"dark_roofs": -0.4, "low_tree_cover": -0.8}}
        self.assertEqual(signature(run(place=cooler_area, household=TIN_FAMILY)),
                         signature(run(place=NO_PROFILE, household=TIN_FAMILY)))

    def test_tin_top_floor_gets_roof_fixes_without_a_roof_cause(self):
        area = {"climate": "semi_arid", "causes": {"low_tree_cover": 0.6, "bare_paved_ground": 0.9}}
        out = run(place=area, household=TIN_FAMILY)
        for fid in ("fam_roof_whitewash", "fam_cool_roof_coating", "fam_modular_roof"):
            self.assertIn(fid, ids(out))

    def test_area_causes_never_trigger_family_fixes(self):
        out = run(place=JAIPUR, household={})
        for fid in ("fam_roof_whitewash", "fam_cool_roof_coating", "fam_modular_roof", "fam_roof_insulation"):
            self.assertNotIn(fid, ids(out))

    def test_area_causes_add_because_lines(self):
        window = next(f for f in run(household=TIN_FAMILY)["fixes"]["today"] if f["id"] == "fam_window_timing")
        codes = [r["code"] for r in window["because"]]
        self.assertEqual(codes[0], "always")
        self.assertIn("area_cause", codes)


class EveryAnswerMatters(unittest.TestCase):
    BASE = {"roof_type": "concrete", "top_floor": False, "vulnerable": False, "devices": [],
            "cross_ventilation": True, "outdoor_worker": False, "has_open_ground": False, "budget": "high"}

    def test_each_household_answer_changes_the_output(self):
        b = self.BASE
        pairs = {
            "vulnerable": (b, {**b, "vulnerable": True}),
            "devices: fan": (b, {**b, "devices": ["fan"]}),
            "devices: cooler": (b, {**b, "devices": ["cooler"]}),
            "cross_ventilation": ({**b, "devices": ["fan"]}, {**b, "devices": ["fan"], "cross_ventilation": False}),
            "outdoor_worker": (b, {**b, "outdoor_worker": True}),
            "top_floor": (b, {**b, "top_floor": True}),
            "roof_type": ({**b, "top_floor": True}, {**b, "top_floor": True, "roof_type": "tin"}),
            "budget": ({**b, "top_floor": True}, {**b, "top_floor": True, "budget": "low"}),
            "has_open_ground": (b, {**b, "has_open_ground": True}),
        }
        for name, (before, after) in pairs.items():
            with self.subTest(answer=name):
                self.assertNotEqual(signature(run(place=NO_PROFILE, household=before)),
                                    signature(run(place=NO_PROFILE, household=after)))

    def test_vulnerable_adds_content_not_just_score(self):
        on = run(household={**TIN_FAMILY, "vulnerable": True})
        off = run(household={**TIN_FAMILY, "vulnerable": False})
        self.assertIn("fam_vulnerable_care", ids(on, "today"))
        self.assertNotIn("fam_vulnerable_care", ids(off, "today"))
        self.assertEqual((on["fan_profile"], off["fan_profile"]), ("vulnerable", "standard"))

    def test_stone_slab_and_asbestos_get_roof_fixes(self):
        for roof in ("stone_slab", "Stone slab", "patti", "asbestos"):
            with self.subTest(roof=roof):
                out = run(household={**TIN_FAMILY, "roof_type": roof})
                self.assertIn("fam_roof_whitewash", ids(out))
                self.assertIn("fam_cool_roof_coating", ids(out))
                self.assertEqual(out["warnings"], [])


class RealTimeInputs(unittest.TestCase):
    def setUp(self):
        self.times, self.rh = [], []
        for day, afternoon in (("2026-05-20", 22), ("2026-05-21", 40)):
            for h in range(24):
                self.times.append(f"{day}T{h:02d}:00")
                self.rh.append(afternoon if 12 <= h < 17 else 68)

    def test_afternoon_humidity_does_not_depend_on_the_hour_opened(self):
        at_6am = afternoon_rh(self.times, self.rh, datetime(2026, 5, 20, 6, 0))
        at_3pm = afternoon_rh(self.times, self.rh, datetime(2026, 5, 20, 15, 0))
        self.assertEqual(at_6am, 22)
        self.assertEqual(at_3pm, 22)
        self.assertEqual(afternoon_rh(self.times, self.rh, datetime(2026, 5, 20, 19, 0)), 40)

    def test_afternoon_humidity_none_when_forecast_is_short(self):
        self.assertIsNone(afternoon_rh(self.times[:13], self.rh[:13], datetime(2026, 5, 20, 6, 0)))

    def test_khus_screen_follows_afternoon_humidity(self):
        dry = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 24})
        humid = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 65})
        self.assertIn("fam_wet_screen", ids(dry, "quick"))
        self.assertEqual(excluded(humid).get("fam_wet_screen"), "too_humid")

    def test_unknown_humidity_leaves_evaporative_fixes_out_with_reason(self):
        out = run(household=TIN_FAMILY, weather={"heat_level": "high"})
        self.assertEqual(excluded(out).get("fam_wet_screen"), "humidity_unknown")
        self.assertNotIn("fam_cooler_dry", ids(out))
        self.assertNotIn("fam_cooler_humid", ids(out))

    def test_cooler_advice_switches_with_humidity(self):
        dry = run(household=TIN_FAMILY, weather={"heat_level": "high", "afternoon_rh_pct": 30})
        humid = run(place={"climate": "humid"}, household=TIN_FAMILY,
                    weather={"heat_level": "high", "afternoon_rh_pct": 75})
        self.assertIn("fam_cooler_dry", ids(dry, "today"))
        self.assertIn("fam_cooler_humid", ids(humid, "today"))
        for out in (dry, humid):  # the other variant is not listed as "left out"
            self.assertFalse({"fam_cooler_dry", "fam_cooler_humid"} & set(excluded(out)))

    def test_colony_checkins_follow_heat_level_not_night_anomaly(self):
        place = {"climate": "semi_arid", "causes": {"dark_roofs": 0.8, "night_heat": 0.7}}
        self.assertIn("col_buddy_checks", ids(run("colony", place, weather=HIGH_DRY), "today"))
        low = run("colony", place, weather={"heat_level": "low", "afternoon_rh_pct": 24})
        self.assertNotIn("col_buddy_checks", ids(low))

    def test_no_forecast_still_gives_household_advice(self):
        out = run(household=TIN_FAMILY, weather=None)
        self.assertIn("fam_window_timing", ids(out))
        self.assertIn("fam_roof_whitewash", ids(out))
        self.assertNotIn("fam_vulnerable_care", ids(out))


class RankingAndExclusions(unittest.TestCase):
    def test_today_order_is_safety_then_core_then_advice(self):
        out = run(household={**TIN_FAMILY, "outdoor_worker": True})
        self.assertEqual(ids(out, "today"), ["fam_vulnerable_care", "fam_outdoor_work", "fam_fan_limits",
                                             "fam_window_timing", "fam_cooler_dry", "fam_night_fan_pull"])

    def test_measured_fix_ranks_above_unmeasured(self):
        self.assertEqual(ids(run(household=TIN_FAMILY), "quick")[0], "fam_roof_whitewash")

    def test_review_numbers_are_not_shown_as_a_range(self):
        trees = next(f for f in run("colony")["fixes"]["long"] if f["id"] == "col_trees_dense_native")
        self.assertEqual(trees["effect"]["kind"], "global_only")
        self.assertIsNone(trees["effect"]["max_c"])
        self.assertNotIn("9", trees["effect"]["text"])

    def test_low_budget_lists_left_out_fixes_with_subsidy_hint(self):
        out = run(household={**TIN_FAMILY, "budget": "low"})
        left = {e["id"]: e["reason"] for e in out["excluded"]}
        self.assertEqual(left["fam_cool_roof_coating"]["code"], "over_budget")
        self.assertTrue(left["fam_cool_roof_coating"]["subsidy_possible"])
        self.assertIn("subsid", left["fam_cool_roof_coating"]["text"])
        self.assertFalse(left["fam_roof_insulation"]["subsidy_possible"])


class InputSafety(unittest.TestCase):
    def test_messy_inputs_are_normalised(self):
        out = run(household={**TIN_FAMILY, "budget": "Low", "devices": "Desert cooler"},
                  weather={"heat_level": "HIGH", "afternoon_rh_pct": 24})
        self.assertEqual(out["warnings"], [])
        self.assertIn("fam_cooler_dry", ids(out, "today"))
        self.assertIn("fam_cool_roof_coating", excluded(out))
        self.assertEqual(run(household={**TIN_FAMILY, "budget": 4000})["excluded"],
                         run(household={**TIN_FAMILY, "budget": "low"})["excluded"])

    def test_bad_inputs_warn_but_never_blank_safety_advice(self):
        out = run(household={**TIN_FAMILY, "budget": "under_5000", "roof_type": "mansion", "vulnerable": "yes"},
                  weather={"heat_level": "high", "afternoon_rh_pct": 150})
        self.assertEqual(len(out["warnings"]), 4)
        self.assertIn("fam_window_timing", ids(out))
        self.assertIn("fam_fan_limits", ids(out))

    def test_wrong_category_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            run(category="families")

    def test_output_is_json_ready(self):
        json.dumps(run(household=TIN_FAMILY, lang="hi"), ensure_ascii=False)


class Hindi(unittest.TestCase):
    def test_titles_reasons_and_effects_are_hindi(self):
        out = run(household=TIN_FAMILY, lang="hi")
        care = out["fixes"]["today"][0]
        self.assertEqual(care["id"], "fam_vulnerable_care")
        for text in [care["title"], care["effect"]["text"], *care["steps"], *(r["text"] for r in care["because"])]:
            self.assertRegex(text, "[\u0900-\u097F]")

    def test_english_fallbacks_are_reported(self):
        out = run(household=TIN_FAMILY, lang="hi")
        self.assertIn("fam_window_timing", out["needs_translation"])
        self.assertNotIn("fam_vulnerable_care", out["needs_translation"])


class BeforeAfterReadings(unittest.TestCase):
    def test_corrects_for_a_hotter_week(self):
        before = [{"indoor_c": i, "outdoor_c": o} for i, o in
                  zip([39.0, 39.4, 38.8, 39.2, 39.1], [40.0, 40.3, 39.9, 40.2, 40.1])]
        after = [{"indoor_c": i, "outdoor_c": o} for i, o in
                 zip([39.5, 39.7, 39.3, 39.6, 39.4], [43.0, 43.1, 42.9, 43.2, 42.8])]
        naive = sum(r["indoor_c"] for r in before) / 5 - sum(r["indoor_c"] for r in after) / 5
        res = estimate_fix_effect(before, after)
        self.assertLess(naive, 0)                 # indoor alone says the fix "failed"
        self.assertEqual(res["status"], "ok")
        self.assertAlmostEqual(res["effect_c"], 2.5)
        self.assertLess(res["range_c"][0], 2.5)

    def test_range_never_narrower_than_half_a_degree(self):
        r_before, r_after = {"indoor_c": 38.0, "outdoor_c": 41.0}, {"indoor_c": 37.0, "outdoor_c": 41.0}
        res = estimate_fix_effect([r_before] * 4, [r_after] * 4)
        self.assertEqual(res["range_c"], [0.5, 1.5])

    def test_needs_three_days_each_side(self):
        r = {"indoor_c": 38.0, "outdoor_c": 41.0}
        self.assertEqual(estimate_fix_effect([r, r], [r, r, r])["status"], "need_more_readings")


class RulesFile(unittest.TestCase):
    def test_rules_have_no_errors(self):
        self.assertEqual(validate_rules(RULES)["errors"], [])


if __name__ == "__main__":
    unittest.main()
