"""Background jobs (spec §9). They run only in the jobs process (`python -m app.jobs`) or through
POST /internal/jobs/{name}; never inside web workers. Every job takes a job_lock row and is idempotent.

Usage (from apps/api):  python -m app.jobs            run the scheduler
                        python -m app.jobs run NAME   run one job now"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from engine import weather

from . import backup, calibrate, config, db, gov, imd, levels, messaging, notify, push, secure
from .models import AccessLog, Feedback, Household, JobLock, NoticeLog, Otp, PushTarget, Reading, Worker, WorkerSession

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger("thandak.jobs")
HOLDER = f"{os.getpid()}-{os.urandom(3).hex()}"
LOCK_MINUTES = 30


def now_ist() -> datetime:
    return datetime.now(IST)


# ------------------------------------------------------------------ locking
def take_lock(name: str, minutes: int = LOCK_MINUTES, holder: str = HOLDER) -> bool:
    until, now = db.utcnow() + timedelta(minutes=minutes), db.utcnow()
    with db.session() as s:
        try:
            with s.begin_nested():
                s.add(JobLock(name=name, holder=holder, locked_until=until))
                s.flush()
            return True
        except IntegrityError:
            pass
        n = s.execute(update(JobLock).where(JobLock.name == name, JobLock.locked_until < now).values(holder=holder, locked_until=until)).rowcount
        return n == 1


def release_lock(name: str, holder: str = HOLDER):
    with db.session() as s:
        s.execute(update(JobLock).where(JobLock.name == name, JobLock.holder == holder).values(locked_until=db.utcnow()))


def run(name: str) -> dict:
    """Run one job under its lock. Returns {"ran": bool, ...result}."""
    if name not in JOBS:
        raise KeyError(name)
    if not take_lock(name):
        return {"ran": False, "reason": "locked"}
    try:
        return {"ran": True, **(JOBS[name]() or {})}
    finally:
        release_lock(name)


# ------------------------------------------------------------------ jobs
def alert_homes(s):
    return list(s.scalars(select(Household).where(Household.alerts_enabled.is_(True), Household.deleted_at.is_(None))))


def prefetch_forecasts() -> dict:
    """17:30 and 05:30: the cells of alert-enabled homes only (app traffic is cached on demand)."""
    with db.session() as s:
        cells = {(h.cell_lat, h.cell_lon) for h in alert_homes(s)}
    ok = failed = 0
    for lat, lon in sorted(cells):
        try:
            weather.fetch(lat, lon)
            ok += 1
        except weather.WeatherUnavailable:
            failed += 1
    return {"cells": len(cells), "ok": ok, "failed": failed}


def evening_alerts(now: datetime | None = None) -> dict:
    """Every 15 minutes 18:00-21:00: homes whose alert hour has come; decide (§7.6) and queue."""
    now = now or now_ist()
    tomorrow = (now + timedelta(days=1)).date()
    queued = skipped = dup = 0
    with db.session() as s:
        for h in alert_homes(s):
            if now.hour < h.alert_hour_ist:
                continue
            try:
                lv = levels.today_and_tomorrow(h.cell_lat, h.cell_lon, h.district_id, h.in_delhi)
            except weather.WeatherUnavailable:
                continue
            if not lv["tomorrow"]:
                continue
            t_idx = lv["tomorrow"]["level_index"]
            today_idx = lv["today"]["level_index"] if lv["today"] else None
            imd = notify.imd_color(s, h.district_id, tomorrow)
            if not notify.alert_worthy(today_idx, t_idx, h.alert_min_level, imd):
                continue
            level = notify.LEVELS[t_idx]
            for target in notify.channels(s, h):
                ok = notify.fatigue_ok(notify.evening_history(s, h, target.kind, tomorrow), tomorrow, t_idx)
                status = "queued" if ok else "skipped_fatigue"
                if notify.queue(s, h, target, tomorrow, "evening", level, "evening_alert", notify.evening_text(h, level), status):
                    queued += ok
                    skipped += not ok
                else:
                    dup += 1
    return {"queued": queued, "skipped_fatigue": skipped, "duplicates": dup}


def morning_work_alerts(now: datetime | None = None) -> dict:
    """06:30: homes with an outdoor work window that is at least High today."""
    now = now or now_ist()
    day = now.date()
    queued = 0
    with db.session() as s:
        for h in alert_homes(s):
            win = h.outdoor_work_window
            if not win or len(win) != 2:
                continue
            try:
                w = weather.fetch(h.cell_lat, h.cell_lon)
            except weather.WeatherUnavailable:
                continue
            idx = levels.window_level(w, day.isoformat(), win[0], win[1])
            if idx < notify.LEVELS.index("high"):
                continue
            level = notify.LEVELS[idx]
            text = messaging.render("morning_work_alert", h.lang, level=notify.level_word(level, h.lang), district=h.district or "",
                                    action=notify.action_line(h.lang), **{"from": win[0], "to": win[1]})
            for target in notify.channels(s, h):
                queued += notify.queue(s, h, target, day, "morning_work", level, "morning_work_alert", text)
    return {"queued": queued}


def _allowed(target: PushTarget) -> bool:
    """With ALERT_TEST_ALLOWLIST set, only those numbers receive anything (dry runs)."""
    if not config.ALERT_TEST_ALLOWLIST:
        return True
    allowed = {secure.phone_hmac(p) for p in (secure.normalise_phone(x) for x in config.ALERT_TEST_ALLOWLIST) if p}
    return target.phone_hmac in allowed


def send_queue(now: datetime | None = None) -> dict:
    """Every minute: send queued rows; retry with backoff; disable a target after 5 failures in a row."""
    now = now or now_ist()
    out = {"sent": 0, "failed": 0, "held": 0, "expired": 0}
    if not config.ALERTS_ENABLED_GLOBAL:
        return {**out, "reason": "ALERTS_ENABLED_GLOBAL is off"}
    if notify.quiet(now):
        if now.hour >= config.QUIET_START_H:       # an evening alert still queued at 22:00 would arrive stale next morning
            with db.session() as s:
                out["expired"] = s.execute(update(NoticeLog).where(NoticeLog.status == "queued", NoticeLog.kind == "evening")
                                           .values(status="failed", error="quiet_hours_expired")).rowcount
        return {**out, "reason": "quiet hours"}
    with db.session() as s:
        rows = s.scalars(select(NoticeLog).where(NoticeLog.status == "queued").where(
            (NoticeLog.next_attempt_at.is_(None)) | (NoticeLog.next_attempt_at <= db.utcnow())).limit(200)).all()
        for n in rows:
            target = s.get(PushTarget, n.target_id) if n.target_id else None
            if not target or not target.active:
                n.status, n.error = "failed", "no_active_target"
                out["failed"] += 1
                continue
            if not _allowed(target):
                out["held"] += 1
                continue
            try:
                if n.channel in ("fcm", "webpush"):
                    sender = push.sender(n.channel)
                    if sender.name != "fake" and messaging.templates()["templates"][n.template_id]["status"].lower() != "approved":
                        raise messaging.SendError("template not approved")
                    n.provider_msg_id = sender.send(target, {"en": "Thandak", "hi": "ठंडक"}[n.lang], n.text, n.id)
                else:
                    prov = messaging.provider(n.channel)
                    if not messaging.template_sendable(n.template_id, prov):
                        raise messaging.SendError("template not approved")
                    phone = secure.decrypt_phone(target.phone_enc, target.key_id)
                    n.provider_msg_id = prov.send(n.channel, phone, n.template_id, n.text)
                n.status, n.sent_at, n.error = "sent", db.utcnow(), None
                target.fail_count, target.last_ok_at = 0, db.utcnow()
                out["sent"] += 1
            except push.Gone as e:                  # the device or browser unsubscribed
                target.active, n.status, n.error = False, "failed", str(e)[:80]
                out["failed"] += 1
            except (messaging.SendError, secure.NotConfigured) as e:
                n.attempts += 1
                target.fail_count += 1
                n.error = str(e)[:80]
                if target.fail_count >= config.TARGET_MAX_FAILS:
                    target.active = False
                if n.attempts >= 3 or not target.active:
                    n.status = "failed"
                    out["failed"] += 1
                else:
                    n.next_attempt_at = db.utcnow() + timedelta(minutes=2 ** n.attempts)
    return out


def _delete_household(s, h: Household, why: str):
    from .models import ConsentEvent
    s.add(ConsentEvent(household_id=h.id, action="deleted", consent_version=h.consent_version, by="self" if why != "worker" else "worker"))
    s.delete(h)


def retention_purge(now: datetime | None = None) -> dict:
    """03:00: hard-delete soft-deleted homes; YES prompt 30 days before RETENTION_DAYS_INACTIVE, delete if no reply;
    delete OTPs older than a day (readings, feedback and access logs join in later phases)."""
    now_u = db.utcnow()
    out = {"deleted": 0, "prompted": 0, "expired_inactive": 0, "otps": 0}
    limit = timedelta(days=config.RETENTION_DAYS_INACTIVE)
    with db.session() as s:
        for h in s.scalars(select(Household).where(Household.deleted_at.is_not(None))).all():
            _delete_household(s, h, "deleted")
            out["deleted"] += 1
        for h in s.scalars(select(Household).where(Household.deleted_at.is_(None))).all():
            idle = now_u - h.last_seen_at
            if h.retention_prompt_at and h.retention_prompt_at >= h.last_seen_at:
                if now_u - h.retention_prompt_at >= timedelta(days=30):
                    _delete_household(s, h, "inactive")
                    out["expired_inactive"] += 1
            elif idle >= limit - timedelta(days=30):
                text = messaging.render("retention_keep", h.lang, district=h.district or "")
                for target in notify.channels(s, h):
                    notify.queue(s, h, target, now_u.date(), "retention", None, "retention_keep", text)
                h.retention_prompt_at = now_u
                out["prompted"] += 1
        out["otps"] = s.execute(delete(Otp).where(Otp.created_at < now_u - timedelta(days=1))).rowcount
        out["access_logs"] = s.execute(delete(AccessLog).where(AccessLog.at < now_u - timedelta(days=365))).rowcount
        out["sessions"] = s.execute(delete(WorkerSession).where(WorkerSession.expires_at < now_u - timedelta(days=30))).rowcount
        out["readings"] = s.execute(delete(Reading).where(Reading.ts < now_u - timedelta(days=730))).rowcount
        out["feedback"] = s.execute(delete(Feedback).where(Feedback.created_at < now_u - timedelta(days=90))).rowcount
    return out


def recalibrate() -> dict:
    """Nightly: homes with readings in the last 30 days (each new reading also recalibrates at once)."""
    since = db.utcnow() - timedelta(days=config.CALIBRATION_WINDOW_DAYS)
    n = 0
    with db.session() as s:
        for hid in set(s.scalars(select(Reading.household_id).where(Reading.ts >= since)).all()):
            h = s.get(Household, hid)
            if h:
                calibrate.recompute(s, h)
                n += 1
    return {"homes": n}


def worker_brief(now: datetime | None = None) -> dict:
    """06:30 (for today) and 19:00 (for tomorrow): each active worker's list of homes to check, by SMS/WhatsApp."""
    from . import workers
    now = now or now_ist()
    day = "today" if now.hour < 12 else "tomorrow"
    for_date = now.date() + timedelta(days=0 if day == "today" else 1)
    queued = 0
    with db.session() as s:
        for wk in s.scalars(select(Worker).where(Worker.active.is_(True))).all():
            homes = s.scalars(select(Household).where(Household.worker_id == wk.id, Household.managed_by == "worker", Household.deleted_at.is_(None))).all()
            ctx = {"id": wk.id, "org_id": wk.org_id, "role": wk.role}
            rows = []
            for h in homes:
                try:
                    a = workers.assess(h, workers.load_people(s, h), day, "en")
                except weather.WeatherUnavailable:
                    continue
                s.add(AccessLog(worker_id=ctx["id"], household_id=h.id, action="brief"))
                if a["persons_at_risk"] or a["level_index"] >= 2:
                    rows.append(a)
            if not rows:
                continue
            rows.sort(key=lambda r: (-r["level_index"], -len(r["persons_at_risk"])))
            text = workers.brief_text(rows, day, "en")
            for t in s.scalars(select(PushTarget).where(PushTarget.worker_id == wk.id, PushTarget.active.is_(True))).all():
                queued += notify.queue_worker(s, wk.id, "en", t, for_date, text)
    return {"queued": queued}


def backup_job() -> dict:
    return backup.make()


JOBS = {"prefetch_forecasts": prefetch_forecasts, "evening_alerts": evening_alerts, "morning_work_alerts": morning_work_alerts,
        "send_queue": send_queue, "retention_purge": retention_purge, "backup": backup_job, "worker_brief": worker_brief,
        "imd_warnings": imd.run, "daily_aggregates": gov.build, "recalibrate": recalibrate}


def scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    sched = BlockingScheduler(timezone=IST)

    def every(name, tag="", **cron):
        sched.add_job(run, CronTrigger(timezone=IST, **cron), args=[name], id=name + tag, max_instances=1, coalesce=True)
    every("prefetch_forecasts", hour="5,17", minute=30)
    every("evening_alerts", hour="18-21", minute="0,15,30,45")
    every("morning_work_alerts", hour=6, minute=30)
    every("send_queue", minute="*")
    every("retention_purge", hour=3, minute=0)
    every("backup", hour=2, minute=0)
    every("worker_brief", "_morning", hour=6, minute=30)
    every("worker_brief", "_evening", hour=19, minute=0)
    every("imd_warnings", "_afternoon", hour=14, minute=30)
    every("imd_warnings", "_night", hour=20, minute=30)
    every("daily_aggregates", hour=23, minute=30)
    every("recalibrate", hour=1, minute=30)
    return sched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db.migrate()
    if sys.argv[1:2] == ["run"] and len(sys.argv) == 3:
        print(run(sys.argv[2]))
    else:
        log.info("thandak jobs: scheduler starting")
        while True:
            try:
                scheduler().start()
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception:                    # keep the jobs process alive; Sentry gets the error
                log.exception("scheduler crashed; restarting in 30 s")
                time.sleep(30)
