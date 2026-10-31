"""Outdoor work card (engine/today.work_plan, "work" in /api/status/individual): only for outdoor workers, only their work
hours, best hours at the window's lowest level, hot hours from the same IMD heat-index rule as work_hours_hot."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import rules, today  # noqa: E402
from tests.test_api_fixes import fake_forecast, status  # noqa: E402

DELHI = dict(lat=28.61, lon=77.21)


def hours_in(rng):
    out = []
    for a, b in rng:
        h = int(a[:2])
        while f"{h:02d}:00" != b:
            out.append(f"{h:02d}:00")
            h = (h + 1) % 24
    return out


def test_no_card_without_an_outdoor_worker():
    assert status(fake_forecast(44, 30, 20, 35), roof="tin_top", **DELHI)["work"] is None


def test_card_covers_the_default_window_and_ranks_hours_by_level():
    w = status(fake_forecast(44, 30, 20, 35), roof="tin_top", vulnerable=["outdoor_worker"], **DELHI)["work"]
    assert w["window"] == list(today.WORK_DEFAULT) and w["window_default"] is True
    assert all(today.in_window(h["time"][11:16], w["window"]) for h in w["hours"])
    by = {h["time"][11:16]: h for h in w["hours"]}
    assert all(by[t]["level_index"] == w["best_level_index"] for t in hours_in(w["best"]))
    assert all(by[t]["level_index"] >= 2 for t in hours_in(w["hot"]))
    for h in w["hours"]:
        assert h["level_index"] == rules.base_from_heat_index(max(h["hi"], h["t"]))
    assert w["avoid_sun"] == {"from_h": 12, "to_h": 15}


def test_a_workers_own_hours_are_used():
    people = [{"age_band": "adult_15_64", "outdoor_work": True, "work_start": "08:00", "work_end": "12:00"}]
    w = status(fake_forecast(44, 30, 20, 35), roof="tin_top", people=people, **DELHI)["work"]
    assert w["window"] == ["08:00", "12:00"] and w["window_default"] is False
    assert {h["time"][11:16] for h in w["hours"]} <= {"08:00", "09:00", "10:00", "11:00"}
