"""The 12 golden safety cases (BACKEND_SPEC §10.1), run through /api/status/individual with fixed forecasts.
Used by tests/test_golden.py and scripts/golden_report.py (which writes docs/launch/GATE_P3_safety.md)."""
from datetime import date

from app import db
from app.models import ImdWarning
from engine import districts
from test_api_fixes import fake_forecast, status

JAIPUR, DELHI, CHENNAI, SHIMLA = (26.91, 75.79), (28.61, 77.21), (13.08, 80.27), (31.10, 77.17)


def _run(where, fc, normal, elevation=None, **answers):
    if elevation is not None:
        fc = {**fc, "elevation": elevation}
    return status(fc, normal=normal, lat=where[0], lon=where[1], **answers)


def _codes(r):
    return [x["code"] for x in r["risk"]["reasons"]]


def _actions(r):
    return [a["code"] for a in r["today_actions"]]


def g1():
    r = _run(JAIPUR, fake_forecast(44, 30, 10, 20), 38.0, roof="rcc_brick_top")
    return r, r["risk"]["level"] == "high", "High"


def g2():
    r = _run(JAIPUR, fake_forecast(44, 30, 10, 20), 41.0, roof="rcc_brick_top")
    return r, r["risk"]["level"] == "moderate", "Moderate"


def g3():
    r = _run(CHENNAI, fake_forecast(36, 29, 75, 85), 37.0, roof="rcc_brick_top")
    return r, r["risk"]["level"] == "extreme" and "wet_bulb_critical" in _codes(r), "Extreme"


def g4():
    r = _run(SHIMLA, fake_forecast(32, 14, 40, 60), 25.0, elevation=2100, roof="rcc_brick_top")
    return r, r["risk"]["level"] == "extreme" and r["indoor"]["numbers_shown"] is False, "Extreme; no exception"


def g5():
    r = _run(DELHI, fake_forecast(38, 28, 30, 45), 38.0, roof="tin_top", vulnerable=["elderly"], devices={})
    p = r["per_person"][0]
    ok = (r["risk"]["level"] == "moderate" and p["higher_risk_today"] and {"extra_care", "go_cooler"} <= set(_actions(r))
          and r["risk"]["home"] == ["tin_roof_top_floor", "vulnerable_person", "no_cooling"])
    return r, ok, "Moderate (home unchanged); higher_risk_today; care + go-somewhere-cooler"


def g6():
    base = _run(JAIPUR, fake_forecast(44, 30, 30, 40), 41.0, roof="rcc_brick_top")
    r = _run(JAIPUR, fake_forecast(44, 30, 30, 40), 41.0, roof="rcc_brick_top", people=[{"age_band": "adult_15_64", "outdoor_work": True}])
    ok = r["fan"]["group"] == "adult" and r["risk"]["level"] == base["risk"]["level"] and "work_hours_hot" in _actions(r)
    return r, ok, "Adult fan limits; level unchanged; work-hours action"


def g7():
    r = _run(DELHI, fake_forecast(42, 30, 30, 45), 38.0, roof="rcc_brick_top", people=[{"age_band": "infant_0_1"}])
    texts = " ".join(a["text"] for a in r["today_actions"] if a.get("person") == 0)
    ok = "infant_care" in _actions(r) and "not even water" in texts and "drink water often" not in texts
    return r, ok, "No generic water line; breastfeeding line shown"


def g8():
    r = _run(JAIPUR, fake_forecast(47, 33, 8, 15), 42.0, roof="rcc_brick_top")
    return r, r["risk"]["level"] == "extreme", "Extreme"


def g9():
    r = _run(DELHI, fake_forecast(42, 31, 45, 55), 38.0, roof="rcc_brick_top", devices={"fan": True, "cooler": True})
    shown = {f["id"] for t in r["fixes"]["fixes"].values() for f in t}
    return r, r["risk"]["level"] == "extreme" and "fam_cooler_dry" not in shown, "Extreme; no 'cooler works well'"


def g10():
    r = _run(DELHI, fake_forecast(40, 29, 30, 45), 38.0, roof="rcc_brick_top",
             people=[{"age_band": "older_65_74", "medicine_classes": ["anticholinergic"]}])
    from engine import verified as V
    want = V.value("fan.limit.anticholinergic")["fan_detrimental_above"]
    return r, r["fan"]["group"] == "anticholinergic" and r["fan"]["limits_c"]["avoid_from"] == want, f"{want:g} °C fan limit from the CSV"


def g11():
    r = _run(DELHI, fake_forecast(43, 31, 25, 40), 38.0, roof="rcc_brick_top", devices={"fan": True, "ac": True},
             power_cut_hours=[["14:00", "16:00"]])
    ac = [a for a in r["today_actions"] if a["code"] == "use_ac_hours"]
    in_cut = any(a <= "14:00" < b or a <= "15:00" < b for x in ac for a, b in x["hours"])
    return r, bool(ac) and not in_cut, "No AC action during the cut"


def g12():
    fc = fake_forecast(37, 27, 25, 40)
    r0 = _run(JAIPUR, fc, 36.0, roof="rcc_brick_top")
    day = date.fromisoformat(_headline_date(r0, fc))
    did = districts.district_at(*JAIPUR)["id"]
    with db.session() as s:
        s.merge(ImdWarning(district_id=did, for_date=day, phenomenon="heat_wave", color="orange"))
    try:
        r = _run(JAIPUR, fc, 36.0, roof="rcc_brick_top")
    finally:
        with db.session() as s:
            s.delete(s.get(ImdWarning, (did, day, "heat_wave")))
    ok = r0["risk"]["level"] == "moderate" and r["risk"]["level"] == "high" and "imd_district_warning" in _codes(r)
    return r, ok, "High, with reason imd_district_warning"


def _headline_date(r, fc):
    days = sorted({h["time"][:10] for h in fc["hourly"]})
    return days[1] if r["risk"]["headline_day"] == "today" else days[2]


CASES = [
    ("G1", "Plains, 44 °C at 10% RH, normal 38 °C", g1),
    ("G2", "Same day, normal 41 °C", g2),
    ("G3", "Coastal, 36 °C at 75% RH", g3),
    ("G4", "Hill, 32 °C, normal 25 °C, room estimate hidden", g4),
    ("G5", "38 °C; tin top floor, elderly person, no devices", g5),
    ("G6", "Outdoor worker only", g6),
    ("G7", "Infant", g7),
    ("G8", "Plains, 47 °C, normal 42 °C", g8),
    ("G9", "42 °C at 45% RH, cooler at home", g9),
    ("G10", "Anticholinergic medicine", g10),
    ("G11", "AC, power cut from 14:00 to 16:00", g11),
    ("G12", "IMD Orange, our rules say Moderate", g12),
]
