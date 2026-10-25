"""Alert rules and jobs (spec §7.6, §9, §10.2 test_notify, §10.3 job lock / retention): when to alert, fatigue,
quiet hours, kill switch, allow-list, no health words in any text, one run per job, retention."""
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import config, db, jobs, levels, messaging, notify
from app.models import ConsentEvent, Household, NoticeLog
from p2_helpers import fake_sender, home, wa

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 5, 20)
EVENING = datetime(2026, 5, 19, 19, 0, tzinfo=IST)


def test_when_to_alert():
    assert notify.alert_worthy(1, 2, "high", None)                 # tomorrow reaches the home's level
    assert not notify.alert_worthy(2, 2, "extreme", None)
    assert notify.alert_worthy(0, 1, "extreme", None)              # up one level and at least Moderate
    assert not notify.alert_worthy(0, 0, "high", None)
    assert notify.alert_worthy(0, 0, "extreme", "orange") and notify.alert_worthy(0, 0, "extreme", "red")


def test_fatigue_first_day_increase_then_every_n_days():
    n = config.ALERT_REPEAT_DAYS
    assert notify.fatigue_ok([], D, 2)                                                       # first day of a run
    assert not notify.fatigue_ok([(D - timedelta(days=1), "high", "sent")], D, 2)             # same level next day
    assert notify.fatigue_ok([(D - timedelta(days=1), "high", "sent")], D, 3)                 # went up
    hist = [(D - timedelta(days=k), "high", "sent" if k == n else "skipped_fatigue") for k in range(1, n + 1)]
    assert notify.fatigue_ok(hist, D, 2)                                                     # n days since the last one
    assert notify.fatigue_ok([(D - timedelta(days=2), "high", "sent")], D, 2)                 # a gap ends the run


def test_quiet_hours():
    assert notify.quiet(datetime(2026, 5, 20, 22, 0, tzinfo=IST)) and notify.quiet(datetime(2026, 5, 20, 5, 59, tzinfo=IST))
    assert not notify.quiet(datetime(2026, 5, 20, 6, 0, tzinfo=IST)) and not notify.quiet(datetime(2026, 5, 20, 21, 59, tzinfo=IST))


def test_no_health_words_in_any_template_or_alert_text():
    values = {"day": "Tomorrow", "level": "Extreme", "district": "Jaipur", "action": notify.action_line("en"), "from": "09:00", "to": "17:00",
              "code": "123456", "minutes": 10, "emergency": "112", "count": 3}
    for tid in messaging.templates()["templates"]:
        for lang in ("en", "hi"):
            text = messaging.render(tid, lang, **values)
            notify.no_health(text)
            assert "{" not in text, (tid, lang)
    try:
        notify.no_health("Dadi's heart medicine")
    except ValueError:
        pass
    else:
        raise AssertionError("health words must be refused")


def _levels(today: int, tomorrow: int):
    names = notify.LEVELS
    return lambda *a, **k: {"weather": {}, "today": {"level": names[today], "level_index": today}, "tomorrow": {"level": names[tomorrow], "level_index": tomorrow}}


def _rows(hid):
    with db.session() as s:
        return list(s.scalars(select(NoticeLog).where(NoticeLog.recipient_key == f"h:{hid}").order_by(NoticeLog.queued_at)))


def test_evening_alert_queued_once_then_sent_only_when_enabled():
    fake = fake_sender()
    hid, _ = home(phone="+919822200001", alert_min_level="high")
    real = levels.today_and_tomorrow
    levels.today_and_tomorrow = _levels(1, 3)
    try:
        assert jobs.evening_alerts(EVENING)["queued"] >= 1
        jobs.evening_alerts(EVENING)                                                         # every 15 min: no duplicate
        rows = _rows(hid)
        assert len(rows) == 1 and rows[0].status == "queued" and rows[0].level == "extreme" and rows[0].for_date == D
        assert jobs.send_queue(datetime(2026, 5, 19, 19, 5, tzinfo=IST))["reason"] == "ALERTS_ENABLED_GLOBAL is off"
        config.ALERTS_ENABLED_GLOBAL = True
        assert jobs.send_queue(datetime(2026, 5, 19, 23, 0, tzinfo=IST))["reason"] == "quiet hours"
        assert _rows(hid)[0].status == "failed"                                              # still queued at 22:00: expired
        with db.session() as s:
            n = s.get(NoticeLog, rows[0].id)
            n.status, n.error = "queued", None
        before = len(fake.sent)
        jobs.send_queue(datetime(2026, 5, 19, 19, 6, tzinfo=IST))
        assert _rows(hid)[0].status == "sent" and len(fake.sent) == before + 1
        assert fake.sent[-1]["text"].startswith("Thandak: Tomorrow, Extreme heat in New Delhi.")
    finally:
        levels.today_and_tomorrow = real
        config.ALERTS_ENABLED_GLOBAL = False


def test_allowlist_holds_everyone_else():
    fake_sender()
    hid, _ = home(phone="+919822200002")
    real = levels.today_and_tomorrow
    levels.today_and_tomorrow = _levels(2, 3)
    config.ALERTS_ENABLED_GLOBAL, config.ALERT_TEST_ALLOWLIST = True, ["+919899999999"]
    try:
        jobs.evening_alerts(EVENING)
        out = jobs.send_queue(datetime(2026, 5, 19, 19, 6, tzinfo=IST))
        assert out["held"] >= 1 and _rows(hid)[0].status == "queued"
    finally:
        levels.today_and_tomorrow = real
        config.ALERTS_ENABLED_GLOBAL, config.ALERT_TEST_ALLOWLIST = False, []


def test_job_lock_lets_one_runner_through():
    assert jobs.take_lock("unit_lock", holder="a") and not jobs.take_lock("unit_lock", holder="b")
    jobs.release_lock("unit_lock", holder="a")
    ran = []
    jobs.JOBS["unit_slow"] = lambda: (ran.append(1), __import__("time").sleep(0.3)) and {}
    try:
        threads = [threading.Thread(target=jobs.run, args=("unit_slow",)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(ran) == 1
    finally:
        del jobs.JOBS["unit_slow"]


def test_retention_prompt_then_delete_but_a_reply_keeps_the_home():
    fake_sender()
    old = db.utcnow() - timedelta(days=config.RETENTION_DAYS_INACTIVE - 10)
    silent, _ = home(phone="+919822200003", last_seen_at=old)
    replier, _ = home(phone="+919822200004", last_seen_at=old)
    assert jobs.retention_purge()["prompted"] >= 2
    assert any(r.kind == "retention" for r in _rows(silent))
    wa("YES", phone="+919822200004")                                    # any reply counts as activity
    with db.session() as s:
        s.get(Household, silent).retention_prompt_at = db.utcnow() - timedelta(days=31)
        s.get(Household, replier).retention_prompt_at = db.utcnow() - timedelta(days=31)
    jobs.retention_purge()
    with db.session() as s:
        assert s.get(Household, silent) is None and s.get(Household, replier) is not None
        assert "deleted" in s.scalars(select(ConsentEvent.action).where(ConsentEvent.household_id == silent)).all()


def test_internal_routes_need_the_secret():
    from p2_helpers import CLIENT
    assert CLIENT.get("/internal/metrics").status_code == 403
    assert CLIENT.get("/internal/metrics", headers={"x-job-secret": "wrong"}).status_code == 403
    m = CLIENT.get("/internal/metrics", headers={"x-job-secret": config.INTERNAL_JOB_SECRET})
    assert m.status_code == 200 and "alerts_last_24h" in m.json() and m.json()["alerts_enabled_global"] is False
    r = CLIENT.post("/internal/jobs/retention_purge", headers={"x-job-secret": config.INTERNAL_JOB_SECRET})
    assert r.status_code == 200 and r.json()["ran"] is True
