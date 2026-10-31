"""Ward cooling scenarios (engine/scenario.py, /api/gov/scenario): physical sign rules, caps, validation and input checks."""
from fastapi.testclient import TestClient

import main
from engine import scenario

CLIENT = TestClient(main.app)


def get(q):
    return CLIENT.get("/api/gov/scenario" + q)


def test_trees_on_built_land_never_warm_a_ward():
    for pp in (1, 10, 30, 50):
        for w in get(f"?tree_pp={pp}").json()["wards"]:
            assert w["day_c"] <= 0 and w["night_c"] <= 0
            assert w["day_band_c"][0] <= w["day_c"] <= w["day_band_c"][1]


def test_more_trees_means_at_least_as_much_cooling():
    a = {w["ward_no"]: w["day_c"] for w in get("?tree_pp=10").json()["wards"]}
    b = {w["ward_no"]: w["day_c"] for w in get("?tree_pp=20").json()["wards"]}
    assert all(b[k] <= a[k] for k in a)


def test_a_ward_cannot_convert_more_land_than_it_has():
    card = scenario._card()
    for w in get("?tree_pp=50&from=bare").json()["wards"]:
        assert w["converted"] <= card["wards"][w["ward_no"]]["bare"] + 1e-9
        assert w["tree_after"] <= 1


def test_model_obeys_its_sign_constraints_and_beats_the_baseline():
    for m in scenario._card()["model"].values():
        assert m["per_share_c"]["tree"] <= 0 and m["per_share_c"]["water"] <= 0
        assert m["cv_mae_c"] < m["baseline_mae_c"]


def test_selected_wards_and_summary():
    d = get("?wards=86,CANT_1&tree_pp=10").json()
    assert d["summary"]["wards"] == 2 and {w["ward_no"] for w in d["wards"]} == {"86", "CANT_1"}
    assert d["summary"]["pop_total"] == sum(w["pop_total"] for w in d["wards"])
    assert "surface_not_air" in d["caveats"]


def test_bad_input_is_rejected():
    assert get("?tree_pp=0").status_code == 422
    assert get("?tree_pp=51").status_code == 422
    assert get("?from=water").status_code == 422
    assert get("?wards=86;drop").status_code == 422


def plan(q):
    return CLIENT.get("/api/gov/plan_trees" + q)


def test_plan_stays_within_budget_and_caps():
    card = scenario._card()
    d = plan("?area_km2=8&max_pp=15&from=built").json()
    assert d["summary"]["area_converted_km2"] <= 8 + 1e-6
    for w in d["wards"]:
        assert w["converted"] <= 0.15 + 1e-6 and w["converted"] <= card["wards"][w["ward_no"]]["built"] + 1e-6
        assert w["day_c"] <= 0


def test_plan_beats_spreading_the_same_land_evenly():
    wards = main._json("gov_rank.json")["wards"]
    best = scenario.optimise(wards, 5, "built", "people", 20)["summary"]["cooling_person_c"]
    total_km2 = sum(w["area_km2"] for w in wards)
    even = scenario.simulate(wards, 5 / total_km2 * 100, "built")["wards"]
    assert best < sum(r["pop_total"] * r["day_c"] for r in even)   # more negative = more cooling where people live


def test_plan_objectives_and_bad_input():
    v = plan("?area_km2=3&objective=vulnerable").json()
    assert v["objective"] == "vulnerable" and v["summary"]["wards"] > 0
    assert plan("?area_km2=0").status_code == 422
    assert plan("?objective=votes").status_code == 422


def test_rupees_appear_only_with_a_verified_cost(monkeypatch):
    wards = main._json("gov_rank.json")["wards"]
    assert scenario.optimise(wards, 2, "built", "people", 20)["cost"] is None       # row is TO VERIFY today
    monkeypatch.setattr(scenario.V, "shown_ok", lambda k: True)
    monkeypatch.setattr(scenario.V, "value", lambda k: {"inr_per_km2": 1000})
    c = scenario.optimise(wards, 2, "built", "people", 20)["cost"]
    assert c["inr"] == 2000 and c["inr_per_km2"] == 1000


def test_a_rupee_budget_places_no_trees_without_a_verified_cost():
    d = plan("?budget_inr=50000000").json()
    assert d["missing"] == ["cost.tree_cover_per_km2"] and d["wards"] == [] and d["cost"] is None
    assert plan("?budget_inr=1&area_km2=2").status_code == 422


def test_a_rupee_budget_for_trees_buys_land_at_the_verified_rate(monkeypatch):
    monkeypatch.setattr(scenario.V, "shown_ok", lambda k: True)
    monkeypatch.setattr(scenario.V, "value", lambda k: {"inr_per_km2": 10_000_000})
    d = plan("?budget_inr=30000000").json()
    assert d["missing"] == [] and d["area_km2"] == 3
    assert d["summary"]["area_converted_km2"] <= 3 + 1e-6 and d["cost"]["inr"] <= 30_000_000


def roofs(q):
    return CLIENT.get("/api/gov/plan_coolroofs" + q)


def test_cool_roofs_place_nothing_until_all_inputs_are_verified():
    d = roofs("?budget_inr=50000000").json()
    assert set(d["missing"]) == set(scenario.ROOF_KEYS) and d["wards"] == [] and d["cost"] is None
    assert d["effect"]["source"]["key"] == "coolroof.indoor_drop" and "not_added_to_trees" in d["caveats"]


ROOF_INPUTS = {"cost.coolroof_per_m2": {"inr_per_m2": 300}, "coolroof.roof_area_per_home_m2": {"m2": 25},
               "household.persons_per_home": {"persons": 5}}


def verified_roof_inputs(monkeypatch):
    real_value, real_ok = scenario.V.value, scenario.V.shown_ok
    monkeypatch.setattr(scenario.V, "shown_ok", lambda k: k in ROOF_INPUTS or real_ok(k))
    monkeypatch.setattr(scenario.V, "value", lambda k: ROOF_INPUTS.get(k) or real_value(k))


def test_cool_roofs_stay_within_budget_and_eligible_homes(monkeypatch):
    verified_roof_inputs(monkeypatch)
    budget = 50_000_000
    d = roofs(f"?budget_inr={budget}").json()
    assert d["missing"] == [] and d["summary"]["homes"] > 0
    assert d["cost"]["inr_per_home"] == 300 * 25 and d["cost"]["inr"] <= budget
    assert sum(w["inr"] for w in d["wards"]) == d["cost"]["inr"]
    assert all(0 < w["homes"] <= w["eligible_homes"] and w["people"] == w["homes"] * 5 for w in d["wards"])
    assert budget - d["cost"]["inr"] < 7500 or len(d["wards"]) == sum(1 for w in main._json("gov_rank.json")["wards"]
                                                                       if w.get("c2011_share_metal_sheet"))


def test_cool_roof_wards_follow_the_goal(monkeypatch):
    verified_roof_inputs(monkeypatch)
    wards = {w["ward_no"]: w for w in main._json("gov_rank.json")["wards"]}
    v = [wards[w["ward_no"]]["hvi"] for w in roofs("?budget_inr=20000000&objective=vulnerable").json()["wards"]]
    assert v == sorted(v, reverse=True)
    e = [wards[w["ward_no"]]["pop_65plus"] / wards[w["ward_no"]]["pop_total"]
         for w in roofs("?budget_inr=20000000&objective=elderly").json()["wards"]]
    assert e == sorted(e, reverse=True)


def test_cool_roof_results_carry_no_ward_surface_temperature(monkeypatch):
    verified_roof_inputs(monkeypatch)
    d = roofs("?budget_inr=10000000").json()
    assert not any(k.endswith("_c") for w in d["wards"] for k in w) and "day_c_pop_weighted" not in d["summary"]
    assert d["effect"]["indoor_drop_c"] == [1.0, 1.38] and d["cost"]["source"]["key"] == "cost.coolroof_per_m2"


def test_cool_roof_bad_input_is_rejected():
    assert roofs("").status_code == 422
    assert roofs("?budget_inr=0").status_code == 422
    assert roofs("?budget_inr=1000&objective=votes").status_code == 422
