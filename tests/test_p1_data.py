"""Data integrity and content rules (BACKEND_SPEC §2 rules 2-3, §7.5, §8.9): manifest, numbers in sentences, prices."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from app import manifest  # noqa: E402
from engine import solutions, verified as V  # noqa: E402

FAMILY = {"roof_type": "asbestos", "top_floor": True, "roof_access": True, "vulnerable": True, "outdoor_worker": True,
          "devices": ["fan", "cooler"], "budget": "high"}


def _all(out):
    return [f for tier in out["fixes"].values() for f in tier]


def test_manifest_matches_and_tampering_stops_prod():
    assert manifest.problems() == [], manifest.problems()
    with tempfile.TemporaryDirectory() as d:
        for f in ("verified_numbers.csv", "MANIFEST.json"):
            shutil.copy(os.path.join(manifest.DATA, f), d)
        m = json.load(open(os.path.join(d, "MANIFEST.json"), encoding="utf-8"))
        m["files"] = {"verified_numbers.csv": m["files"]["verified_numbers.csv"]}
        json.dump(m, open(os.path.join(d, "MANIFEST.json"), "w", encoding="utf-8"))
        assert manifest.verify(prod=True, data_dir=d) == []
        with open(os.path.join(d, "verified_numbers.csv"), "a", encoding="utf-8") as fh:
            fh.write("evil,1,,,,,,Verified,,\n")
        try:
            manifest.verify(prod=True, data_dir=d)
        except RuntimeError:
            pass
        else:
            raise AssertionError("a tampered data file must stop a prod start")
        assert manifest.verify(prod=False, data_dir=d)        # dev: logged, returned


def test_catalogue_has_no_errors_and_numbers_resolve():
    assert solutions.validate_rules()["errors"] == []
    for lang in ("en", "hi"):
        out = solutions.recommend("family", {"climate": "semi_arid"}, FAMILY, {"heat_level": "extreme", "afternoon_twb_c": 20}, lang)
        text = json.dumps(out, ensure_ascii=False)
        assert "{n:" not in text
        for cat in ("colony", "government"):
            assert "{n:" not in json.dumps(solutions.recommend(cat, {"climate": "arid"}, None, {"heat_level": "extreme"}, lang), ensure_ascii=False)


def test_number_from_an_unverified_row_is_refused():
    try:
        solutions.fill_numbers("{n:cost.lime_per_kg:inr_per_kg_min:0}")
    except ValueError:
        pass
    else:
        raise AssertionError("an UNVERIFIED number must not be shown")
    assert solutions.fill_numbers("{n:coolroof.indoor_drop:india_high:1}") == f"{V.value('coolroof.indoor_drop')['india_high']:.1f}"


def test_no_unverified_price_is_shown():
    out = solutions.recommend("family", {"climate": "semi_arid"}, FAMILY, {"heat_level": "high"})
    for f in _all(out):
        assert "₹" not in (f["cost_text"] or ""), f["id"]


def test_asbestos_caution_includes_drilling():
    out = solutions.recommend("family", {"climate": "semi_arid"}, FAMILY, {"heat_level": "high"})
    for f in _all(out):
        if f["id"] in ("lime_whitewash", "cool_roof_coating"):
            assert "drill" in f["caution"], f["id"]
