"""Table-driven safety tests: fan advice and risk levels must follow verified_numbers.csv exactly.
Run from heat-india/:  python tests/test_rules.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from engine import rules  # noqa: E402
from engine import verified as V  # noqa: E402


def rows(t, rh, n=24):
    from engine.heat import heat_index_c, wet_bulb_c
    return [{"time": f"2026-05-20T{h:02d}:00", "t": t, "rh": rh, "hi": heat_index_c(t, rh), "twb": wet_bulb_c(t, rh)} for h in range(n)]


def test_fan_thresholds_from_table():
    older = V.value("fan.limit.older")
    healthy = V.value("fan.limit.healthy")
    cases = [  # (temp, group, expected)
        (older["fan_alone_not_enough_above"] - 0.1, "older", "fan_helps"),
        (older["fan_alone_not_enough_above"], "older", "fan_not_enough_alone"),
        (older["fan_detrimental_above"] - 0.1, "older", "fan_not_enough_alone"),
        (older["fan_detrimental_above"], "older", "avoid_fan_alone"),
        (healthy["fan_helps_below"] - 0.1, "adult", "fan_not_enough_alone"),
        (healthy["fan_helps_below"], "adult", "avoid_fan_alone"),
        (30.0, "adult", "fan_helps"),
    ]
    for t, g, exp in cases:
        assert rules.fan_state(t, g) == exp, (t, g, rules.fan_state(t, g), exp)


def test_older_limit_never_looser_than_healthy():
    assert rules.fan_limits("older")["avoid_from"] <= rules.fan_limits("adult")["avoid_from"]


def test_household_factors_are_listed_not_added_to_the_level():
    r = rules.risk(rows(42, 30), rows(42, 30), rows(42, 30))
    assert r["level_index"] == rules.base_from_heat_index(max(r["hi_max"], r["tmax"])), r   # weather only
    assert rules.home_factors("tin_top", ["elderly"], {}) == ["tin_roof_top_floor", "vulnerable_person", "no_cooling"]
    assert rules.home_factors("rcc_brick_top", [], {"fan": True}) == []


def test_heatwave_tmax_forces_at_least_high():
    hw = V.value("imd.heatwave")["hw_actual_tmax"]
    r = rules.risk(rows(hw, 8), rows(30, 20), rows(30, 20))
    assert r["level_index"] >= 2, r


def test_wet_bulb_critical_is_extreme():
    r = rules.risk(rows(36, 80), rows(36, 80), rows(36, 80))
    assert r["twb_max"] >= V.value("wet_bulb.danger")["critical_humid_young_mean"]
    assert r["level"] == "extreme", r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
