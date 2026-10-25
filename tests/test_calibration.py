"""Learning the home (spec §5.6-5.8, §6.4, §7.4, §10.2 test_calibration): clipping, kitchen exclusion, day/night
split, n >= 2 before applying, outliers flagged not dropped, readings API, feedback, fix progress, room numbers
outside Delhi once a home is calibrated."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import calibrate, config, db
from app.models import Household, Reading
from engine import weather
from p2_helpers import CLIENT

IST = ZoneInfo("Asia/Kolkata")
NEW = {"consent": {"version": "draft-1", "accepted": True}, "lang": "en", "place": {"lat": 26.91, "lon": 75.79},
       "home": {"roof": "rcc_brick_top", "fan": True}, "summary": {"higher_risk": False}, "alerts": {"enabled": False}}


class Synthetic(weather.WeatherProvider):
    """A forecast around the current hour, inside the room model's training range (so predictions exist)."""
    name = "synthetic"

    def get(self, lat, lon):
        """Like the live forecast: 2 past days (the model needs 24 h of lags) and the days ahead."""
        start = datetime.now(IST).replace(tzinfo=None, minute=0, second=0, microsecond=0) - timedelta(hours=48)
        rows = []
        for k in range(48 + 72):
            ts = start + timedelta(hours=k)
            frac = max(0.0, 1 - abs(ts.hour - 15) / 9)
            rows.append({"time": ts.strftime("%Y-%m-%dT%H:00"), "t": round(26 + 10 * frac, 1), "rh": 40 if 12 <= ts.hour < 17 else 50,
                         "sw": 800 * frac, "ws": 2.0})
        return {"hourly": rows, "daily_tmax": {}, "elevation": 400}


@contextmanager
def saved_home():
    old = config.HOUSEHOLDS_ENABLED
    config.HOUSEHOLDS_ENABLED = True
    weather.set_provider(Synthetic())
    try:
        r = CLIENT.post("/api/v1/households", json=NEW).json()
        yield r["household_id"], {"Authorization": "Bearer " + r["token"]}
    finally:
        config.HOUSEHOLDS_ENABLED = old


def test_shrinkage_clipping_and_minimum_readings():
    k = calibrate.validated()["k_day"]
    assert calibrate.shrunk_bias([2.0], k) is None                                     # one reading: nothing applied
    assert calibrate.shrunk_bias([2.0, 2.0], k) == round(4.0 / (2 + k), 2)            # shrunk towards 0
    with_typo = calibrate.shrunk_bias([1.0, 1.2, 0.8, 1.1, 0.9, 25.0], k)              # one bad reading is clipped
    assert with_typo < 1.5
    assert calibrate.outlier(25.0, [1.0, 1.2, 0.8, 1.1, 0.9]) and not calibrate.outlier(25.0, [1.0, 1.2, 0.8])


def test_calibration_is_validated_in_the_model_card():
    v = calibrate.validated()
    assert v and v["decision"].startswith("ship") and all(r["change_c"] < 0 for r in v["replay"])


def _reading(headers, hours_ago, indoor, room="bedroom", fix_id=None):
    ts = (datetime.now(IST) - timedelta(hours=hours_ago)).replace(minute=0, second=0, microsecond=0).isoformat()
    body = {"ts": ts, "room": room, "indoor_c": indoor}
    if fix_id:
        body["fix_id"] = fix_id
    return CLIENT.post("/api/v1/households/me/readings", json=body, headers=headers)


def test_readings_fill_outdoor_and_model_and_split_day_night_without_kitchen():
    with saved_home() as (hid, H):
        r = _reading(H, 3, 33.0)
        assert r.status_code == 201, r.text
        rd = r.json()["reading"]
        assert rd["outdoor_c"] is not None and rd["predicted_c"] is not None and rd["period"] in ("day", "night")
        k = _reading(H, 4, 40.0, room="kitchen").json()["reading"]
        assert k["used_for_calibration"] is False                                      # kitchens never calibrate
        for h in range(5, 30):
            _reading(H, h, 34.0)
        with db.session() as s:
            home = s.get(Household, hid)
            assert home.calib_n_day >= 2 and home.calib_n_night >= 2
            assert home.calib_bias_day_c is not None and home.calib_bias_night_c is not None
        assert _reading(H, 2, 9.0).status_code == 422 and _reading(H, 2, 56.0).status_code == 422
        assert _reading(H, 80, 33.0).status_code == 422                               # older than 2 days
        listed = CLIENT.get("/api/v1/households/me/readings", headers=H).json()["readings"]
        before = len(listed)
        assert CLIENT.delete(f"/api/v1/households/me/readings/{listed[0]['id']}", headers=H).status_code == 204
        assert len(CLIENT.get("/api/v1/households/me/readings", headers=H).json()["readings"]) == before - 1


def test_calibrated_home_outside_delhi_gets_room_numbers_after_five_readings():
    with saved_home() as (hid, H):
        first = CLIENT.post("/api/v1/households/me/status", json={}, headers=H).json()
        assert first["indoor"]["numbers_shown"] is False                                 # Jaipur, not calibrated yet
        for h in range(3, 12):
            _reading(H, h, 35.0)
        st = CLIENT.post("/api/v1/households/me/status", json={}, headers=H).json()
        assert st["calibration"]["applied"] and st["calibration"]["n_day"] + st["calibration"]["n_night"] >= 5
        assert st["indoor"]["numbers_shown"] is True and st["indoor"]["next24"]


def test_feedback_one_answer_a_day_and_no_free_text():
    with saved_home() as (hid, H):
        today = datetime.now(IST).date().isoformat()
        assert CLIENT.post("/api/v1/households/me/feedback", json={"for_date": today, "night_feel": "hot"}, headers=H).status_code == 204
        assert CLIENT.post("/api/v1/households/me/feedback", json={"for_date": today, "night_feel": "could_not_sleep"}, headers=H).status_code == 204
        assert CLIENT.post("/api/v1/households/me/feedback", json={"for_date": today, "night_feel": "hot", "note": "my head hurts"},
                           headers=H).status_code == 422
        from app.models import Feedback
        with db.session() as s:
            rows = s.scalars(select(Feedback).where(Feedback.household_id == hid)).all()
            assert len(rows) == 1 and rows[0].night_feel == "could_not_sleep"


def test_fix_progress_measures_the_effect_from_readings():
    with saved_home() as (hid, H):
        done = (datetime.now(IST) - timedelta(hours=20)).date()
        with db.session() as s:                                                # readings across several days, before and after
            for d in range(1, 6):
                s.add(Reading(household_id=hid, ts=datetime.combine(done - timedelta(days=d), datetime.min.time()) + timedelta(hours=15),
                              room="bedroom", indoor_c=38.0, outdoor_c=36.0, source="thermometer", period="day"))
                s.add(Reading(household_id=hid, ts=datetime.combine(done + timedelta(days=d - 1), datetime.min.time()) + timedelta(hours=15),
                              room="bedroom", indoor_c=36.5, outdoor_c=36.0, source="thermometer", period="day"))
        r = CLIENT.put("/api/v1/households/me/fixes/lime_whitewash", json={"status": "done", "done_at": done.isoformat()}, headers=H).json()
        assert r["status"] == "done" and r["measured_effect_c"] == 1.5
        assert CLIENT.put("/api/v1/households/me/fixes/not_a_fix", json={"status": "planned"}, headers=H).status_code == 404
        prog = CLIENT.post("/api/v1/households/me/status", json={}, headers=H).json()["fix_progress"]
        assert prog[0]["fix_id"] == "lime_whitewash" and prog[0]["measured_effect_c"] == 1.5
