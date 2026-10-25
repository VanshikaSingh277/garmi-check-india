"""Per-person advice (BACKEND_SPEC §5.3, §7.2-7.3, §10.2 test_people_rules)."""
import json
import re

from pydantic import ValidationError

from engine import people, rules, today
from test_api_fixes import fake_forecast, status

DELHI = dict(lat=28.61, lon=77.21)


def test_old_form_maps_to_people_without_guessing_conditions():
    got = people.from_vulnerable(["elderly", "child", "pregnant", "chronic", "outdoor_worker", "elderly"])
    assert got == [{"age_band": "older_65_74"}, {"age_band": "child_1_5"}, {"age_band": "adult_15_64", "pregnant": True},
                   {"age_band": "adult_15_64", "conditions": ["unspecified"]}, {"age_band": "adult_15_64", "outdoor_work": True}]


def test_fan_groups():
    assert people.fan_group({"age_band": "older_75_plus"}) == ("older", False)
    assert people.fan_group({"age_band": "older_65_74", "medicine_classes": ["anticholinergic"]}) == ("anticholinergic", False)
    for p in ({"age_band": "infant_0_1"}, {"age_band": "adult_15_64", "pregnant": True}, {"age_band": "adult_15_64", "conditions": ["kidney"]},
              {"age_band": "adult_15_64", "medicine_classes": ["water_pill"]}):
        assert people.fan_group(p) == ("older", True), p
    assert people.fan_group({"age_band": "adult_15_64", "outdoor_work": True}) == ("adult", False)
    assert rules.strictest(["adult", "older", "anticholinergic"]) == "anticholinergic"
    assert rules.fan_limits("anticholinergic")["avoid_from"] < rules.fan_limits("older")["avoid_from"] < rules.fan_limits("adult")["avoid_from"]


def test_household_fan_advice_uses_the_strictest_person():
    r = status(fake_forecast(40, 29, 30, 45), roof="rcc_brick_top", devices={"fan": True},
               people=[{"age_band": "adult_15_64"}, {"age_band": "older_65_74", "medicine_classes": ["anticholinergic"]}], **DELHI)
    assert r["fan"]["group"] == "anticholinergic" and r["fan"]["precautionary"] is False


def test_no_per_person_level_only_higher_risk_today():
    r = status(fake_forecast(40, 29, 30, 45), roof="tin_top", people=[{"age_band": "older_65_74"}], **DELHI)
    p = r["per_person"][0]
    assert "level" not in p and isinstance(p["higher_risk_today"], bool) and p["reasons"] == ["older"]


def test_ac_covers_hours_outside_power_cuts_only():
    r = status(fake_forecast(43, 31, 25, 40), roof="rcc_brick_top", devices={"fan": True, "ac": True}, power_cut_hours=[["13:00", "17:00"]],
               people=[{"age_band": "older_65_74"}], **DELHI)
    person = r["per_person"][0]
    for a, b in person["fan_avoid_hours"] + person["fan_not_enough_hours"]:
        assert a >= "13:00" and b <= "17:00", (a, b)                # fan warnings only while the AC has no power
    ac = next(x for x in r["today_actions"] if x["code"] == "use_ac_hours")
    assert all(not (a < "17:00" and b > "13:00") for a, b in ac["hours"])


def test_without_cooling_never_tell_them_to_switch_off_the_fan():
    r = status(fake_forecast(41, 30, 30, 45), roof="tin_top", devices={"fan": True}, people=[{"age_band": "older_65_74"}], **DELHI)
    text = " ".join(a["text"] for a in r["today_actions"])
    assert "wet" in text and "use the fan" in text and "turn off" not in text.lower()


def test_nickname_is_echoed_only_in_the_answer_and_hostile_ones_are_rejected():
    r = status(fake_forecast(40, 29, 30, 45), roof="tin_top", people=[{"age_band": "older_65_74", "nickname": "Dadi"}], **DELHI)
    assert r["per_person"][0]["label"] == "Dadi"
    for bad in ("<script>", "Dadi\n", "x" * 31, "a{b}"):
        try:
            status(fake_forecast(40, 29, 30, 45), roof="tin_top", people=[{"age_band": "older_65_74", "nickname": bad}], **DELHI)
        except ValidationError:
            continue
        raise AssertionError(f"nickname {bad!r} accepted")
    hindi = status(fake_forecast(40, 29, 30, 45), roof="tin_top", people=[{"age_band": "older_65_74", "nickname": "दादी"}], **DELHI)
    assert hindi["per_person"][0]["label"] == "दादी"


def test_people_fields_are_strict():
    for bad in ({"age_band": "teen"}, {"age_band": "adult_15_64", "conditions": ["cancer"]}, {"age_band": "adult_15_64", "medicine_classes": ["aspirin"]},
                {"age_band": "adult_15_64", "work_start": "25:00"}, {"age_band": "adult_15_64", "name": "Ravi"}):
        try:
            status(fake_forecast(40, 29, 30, 45), roof="tin_top", people=[bad], **DELHI)
        except ValidationError:
            continue
        raise AssertionError(f"person {bad} accepted")


def test_action_texts_exist_in_both_languages_with_no_placeholders_left():
    acts = today.texts()["actions"]
    for code, v in acts.items():
        assert v.get("en") and v.get("hi"), code
        assert re.search(r"[ऀ-ॿ]", v["hi"]), code
    r = status(fake_forecast(42, 31, 30, 45), roof="tin_top", lang="hi", devices={},
               people=[{"age_band": "infant_0_1"}, {"age_band": "older_65_74", "lives_alone": True, "medicine_classes": ["water_pill"]},
                       {"age_band": "adult_15_64", "outdoor_work": True, "conditions": ["kidney"]}], **DELHI)
    blob = json.dumps(r["today_actions"], ensure_ascii=False)
    assert "{" not in blob.replace('{"', "").replace("{}", "")
    assert all(re.search(r"[ऀ-ॿ]", a["text"]) for a in r["today_actions"])
