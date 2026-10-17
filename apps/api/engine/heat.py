"""Heat index (NWS Rothfusz) and wet-bulb (Stull 2011). Same code as pipelines/common/heat_formulas.py, tested."""
import math


def _f(c):
    return c * 9 / 5 + 32


def _c(f):
    return (f - 32) * 5 / 9


def heat_index_c(t_c: float, rh: float) -> float:
    t = _f(t_c)
    simple = 0.5 * (t + 61.0 + ((t - 68.0) * 1.2) + (rh * 0.094))
    if (simple + t) / 2.0 < 80.0:
        return _c((simple + t) / 2.0)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
          - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    if rh < 13.0 and 80.0 <= t <= 112.0:
        hi -= ((13.0 - rh) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
    elif rh > 85.0 and 80.0 <= t <= 87.0:
        hi += ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return _c(hi)


def wet_bulb_c(t_c: float, rh: float) -> float:
    return (t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + math.atan(t_c + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)
