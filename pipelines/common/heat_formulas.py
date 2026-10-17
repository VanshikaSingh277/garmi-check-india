"""Heat index and wet-bulb formulas.

Sources (verified 2026-10-15, see docs/verified_numbers.csv / docs/sources.md):
- Heat index: US NWS / WPC, "The Heat Index Equation" (Rothfusz regression + adjustments)
  https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
- Wet-bulb: Stull R. (2011) J. Appl. Meteor. Climatol. 50(11):2267-2269, doi:10.1175/JAMC-D-11-0143.1
  Valid for RH 5-99 % and T -20..50 degC; MAE < 0.3 degC.
Both use AIR temperature and relative humidity (never satellite surface temperature).
"""
from __future__ import annotations

import math


def c_to_f(t_c: float) -> float:
    return t_c * 9.0 / 5.0 + 32.0


def f_to_c(t_f: float) -> float:
    return (t_f - 32.0) * 5.0 / 9.0


def heat_index_c(t_c: float, rh: float) -> float:
    """NWS heat index (deg C) from air temperature (deg C) and relative humidity (%)."""
    t = c_to_f(t_c)
    # Step 1: simple formula, averaged with temperature
    simple = 0.5 * (t + 61.0 + ((t - 68.0) * 1.2) + (rh * 0.094))
    if (simple + t) / 2.0 < 80.0:
        return f_to_c((simple + t) / 2.0)
    # Step 2: full Rothfusz regression
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
          - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
          + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    # Step 3: adjustments
    if rh < 13.0 and 80.0 <= t <= 112.0:
        hi -= ((13.0 - rh) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
    elif rh > 85.0 and 80.0 <= t <= 87.0:
        hi += ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return f_to_c(hi)


def wet_bulb_stull_c(t_c: float, rh: float) -> float:
    """Stull (2011) wet-bulb temperature (deg C). Outside 5-99 % RH / -20..50 degC the result is flagged by callers."""
    return (t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
            + math.atan(t_c + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
            - 4.686035)


def stull_valid(t_c: float, rh: float) -> bool:
    return 5.0 <= rh <= 99.0 and -20.0 <= t_c <= 50.0
