"""Government numbers and IMD warnings (spec §5.11, §6.8, §7.1, §10.2 test_aggregates): NULL below AGG_MIN_COUNT,
only shared and worker-managed homes count, "among Thandak users", IMD off until onboarding, never below IMD."""
import json
import os
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import config, db, gov, imd, jobs
from app.models import DailyAggregate, Household, ImdWarning
from engine import districts, weather
from p2_helpers import CLIENT, Recorded

IST = ZoneInfo("Asia/Kolkata")
JAIPUR = districts.district_at(26.91, 75.79)["id"]


def _homes(n, shared=True, district=JAIPUR, counts=None):
    with db.session() as s:
        for _ in range(n):
            s.add(Household(cell_lat=26.9, cell_lon=75.8, district_id=district, district="Jaipur", share_counts=shared,
                            counts=counts if shared else None, managed_by="self", consent_version="draft-1"))


def test_small_counts_are_null_and_only_shared_homes_count():
    weather.set_provider(Recorded("jaisalmer"))
    did = "test-district-agg"
    _homes(config.AGG_MIN_COUNT + 2, shared=True, district=did, counts={"older": 1})
    _homes(50, shared=False, district=did)                                  # not shared: never counted
    gov.build(datetime.now(IST).date())
    with db.session() as s:
        row = s.get(DailyAggregate, (datetime.now(IST).date(), did))
    assert row.households == config.AGG_MIN_COUNT + 2                        # the 50 unshared homes aren't in it
    assert row.alerts_sent is None and row.nights_could_not_sleep is None     # 0 < 10: stored as NULL
    small = "test-district-small"
    _homes(3, district=small)
    gov.build(datetime.now(IST).date())
    with db.session() as s:
        assert s.get(DailyAggregate, (datetime.now(IST).date(), small)).households is None


def test_gov_endpoints_say_among_thandak_users():
    r = CLIENT.get("/api/v1/gov/today").json()
    assert "Among Thandak users" in r["note"] and r["min_count"] == config.AGG_MIN_COUNT
    t = CLIENT.get("/api/v1/gov/trend", params={"district_id": "test-district-agg", "from": "2026-01-01", "to": "2026-12-31"}).json()
    assert "Among Thandak users" in t["note"]
    assert CLIENT.get("/api/v1/gov/trend", params={"district_id": "x", "from": "2025-01-01", "to": "2026-12-31"}).status_code == 422


def test_imd_off_until_onboarding_then_stores_normalised_warnings():
    assert "IMD_ENABLED is off" in jobs.imd.run()["skipped"]
    sample = {"issued_at": "2026-05-20T13:00:00", "source_url": "test-fixture (Thandak normalised format, not IMD's response)",
              "warnings": [{"district_id": JAIPUR, "date": "2026-05-21", "phenomenon": "heat_wave", "color": "red"},
                           {"district_id": JAIPUR, "date": "2026-05-21", "phenomenon": "heat_wave", "color": "purple"},
                           {"district_id": JAIPUR, "phenomenon": "heat_wave", "color": "orange"}]}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "imd.json")
        with open(path, "w") as f:
            json.dump(sample, f)
        config.IMD_ENABLED = True
        imd.set_provider(imd.NormalisedFile(path))
        try:
            out = imd.run()
        finally:
            config.IMD_ENABLED = False
            imd.set_provider(None)
    assert out == {"stored": 1, "skipped": 2}
    assert CLIENT.get("/api/health").json()["imd_last_ok_at"] is not None
    with db.session() as s:
        w = s.get(ImdWarning, (JAIPUR, date(2026, 5, 21), "heat_wave"))
        assert w.color == "red"
        s.delete(w)
