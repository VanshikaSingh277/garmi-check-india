"""Table-driven checks against published reference values. Run: python -m pytest tests/ (or python tests/test_heat_formulas.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines", "common"))
from heat_formulas import heat_index_c, wet_bulb_stull_c, c_to_f, f_to_c  # noqa: E402


def test_stull_reference_example():
    # Stull (2011) abstract: T = 20 degC, RH = 50 % -> Tw = 13.7 degC
    assert abs(wet_bulb_stull_c(20.0, 50.0) - 13.7) < 0.05


def test_delhi_hap_examples():
    # Delhi Heat Action Plan 2024-25 text: 34 degC @ 75 % RH -> HI 49 degC; same effect at 31 degC @ 100 % RH
    assert abs(heat_index_c(34.0, 75.0) - 49.0) < 1.0
    assert abs(heat_index_c(31.0, 100.0) - 49.0) < 1.0


def test_heat_index_low_range_uses_simple_formula():
    # Below ~80 degF the NWS simple formula (averaged with T) is used; HI should stay close to T
    t_c = f_to_c(75.0)
    assert abs(c_to_f(heat_index_c(t_c, 40.0)) - 75.0) < 3.0


def test_heat_index_increases_with_humidity():
    t_c = f_to_c(96.0)
    vals = [heat_index_c(t_c, rh) for rh in (20, 40, 60, 80)]
    assert vals == sorted(vals)


def test_low_humidity_adjustment_applied():
    # RH < 13 % and 80-112 degF -> adjustment subtracted (HI lower than unadjusted regression)
    t = 100.0
    rh = 5.0
    unadj = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
             - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    assert c_to_f(heat_index_c(f_to_c(t), rh)) < unadj


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
