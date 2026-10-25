"""Alert decision and queueing (spec §7.6).
- Evening alert for tomorrow when: tomorrow's level >= the home's alert_min_level, or tomorrow is at least one level
  above today and at least Moderate, or IMD shows Orange or Red.
- Fatigue: in a run of alert days, send on the first day, on any increase, then every ALERT_REPEAT_DAYS days.
- Quiet hours: nothing is sent 22:00-06:00 IST. Duplicates are stopped by notice_log's unique key.
- Texts never carry health details (spec §2 rule 7)."""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from engine import solutions

from . import config, messaging
from .models import Household, ImdWarning, NoticeLog, PushTarget

IST = ZoneInfo("Asia/Kolkata")
LEVELS = ["low", "moderate", "high", "extreme"]
# words that must never appear in a push / SMS / WhatsApp text (conditions, medicines, pregnancy)
HEALTH_WORDS = re.compile(r"heart|kidney|diabet|pregnan|medicine|medication|tablet|pill|disease|illness|asthma|"
                          r"दिल|किडनी|गुर्दा|शुगर|मधुमेह|गर्भ|दवा|बीमार|दमा", re.I)


def quiet(now: datetime | None = None) -> bool:
    h = (now or datetime.now(IST)).hour
    return h >= config.QUIET_START_H or h < config.QUIET_END_H


def imd_color(s, district_id: str | None, day: date) -> str | None:
    if not district_id:
        return None
    rows = s.scalars(select(ImdWarning.color).where(ImdWarning.district_id == district_id, ImdWarning.for_date == day)).all()
    order = ["green", "yellow", "orange", "red"]
    return max(rows, key=order.index) if rows else None


def alert_worthy(today: int | None, tomorrow: int, min_level: str, imd: str | None) -> bool:
    if tomorrow >= LEVELS.index(min_level):
        return True
    if today is not None and tomorrow >= today + 1 and tomorrow >= LEVELS.index("moderate"):
        return True
    return imd in ("orange", "red")


def fatigue_ok(history: list[tuple[date, str | None, str]], day: date, level: int) -> bool:
    """history: (for_date, level, status) of earlier evening alerts for this recipient. A day counts as part of the
    run when it was alert-worthy (queued, sent, opened, failed or skipped_fatigue)."""
    by_day = {d: (lv, st) for d, lv, st in history}
    run, d = [], day - timedelta(days=1)
    while d in by_day:
        run.append(d)
        d -= timedelta(days=1)
    if not run:
        return True                                                    # first day of a run
    if any(LEVELS.index(by_day[x][0] or "low") < level for x in run[:1]):
        return True                                                    # level went up since yesterday
    last_sent = next((x for x in run if by_day[x][1] in ("queued", "sent", "opened")), None)
    if last_sent is None:
        return True
    return (day - last_sent).days >= config.ALERT_REPEAT_DAYS


def action_line(lang: str) -> str:
    """One general action from the catalogue, the same for everyone (no health details)."""
    fix = next(f for f in solutions.catalogue()["fixes"] if f["id"] == "night_ventilation")
    return solutions.fill_numbers(fix.get(f"title_{lang}") or fix["title_en"]).rstrip(".") + "."


def level_word(level: str, lang: str) -> str:
    v = solutions.catalogue()["labels"]["value"]["heat_level"][level]
    return v.get(lang) or v["en"]


def no_health(text: str) -> str:
    if HEALTH_WORDS.search(text):
        raise ValueError("message text contains a health word")
    return text


def queue(s, h: Household, target: PushTarget, day: date, kind: str, level: str | None, template_id: str, text: str,
          status: str = "queued") -> bool:
    """Insert one notice_log row; False when this recipient already has one for that day, kind and channel."""
    row = NoticeLog(recipient_key=f"h:{h.id}", target_id=target.id, for_date=day, kind=kind, level=level, channel=target.kind,
                    template_id=template_id, lang=h.lang, text=no_health(text), status=status)
    try:
        with s.begin_nested():
            s.add(row)
            s.flush()
        return True
    except IntegrityError:
        return False


def queue_worker(s, worker_id: str, lang: str, target: PushTarget, day: date, text: str) -> bool:
    """The worker brief (spec §6.7): one per worker, day and channel."""
    row = NoticeLog(recipient_key=f"w:{worker_id}", target_id=target.id, for_date=day, kind="worker_brief", channel=target.kind,
                    template_id="worker_brief_head", lang=lang, text=no_health(text), status="queued")
    try:
        with s.begin_nested():
            s.add(row)
            s.flush()
        return True
    except IntegrityError:
        return False


def channels(s, h: Household) -> list[PushTarget]:
    return list(s.scalars(select(PushTarget).where(PushTarget.household_id == h.id, PushTarget.active.is_(True),
                                                   PushTarget.kind.in_(("whatsapp", "sms", "fcm", "webpush")))))


def evening_history(s, h: Household, channel: str, day: date):
    rows = s.execute(select(NoticeLog.for_date, NoticeLog.level, NoticeLog.status).where(
        NoticeLog.recipient_key == f"h:{h.id}", NoticeLog.kind == "evening", NoticeLog.channel == channel,
        NoticeLog.for_date >= day - timedelta(days=30), NoticeLog.for_date < day)).all()
    return [(r[0], r[1], r[2]) for r in rows]


def evening_text(h: Household, level: str) -> str:
    day = {"en": "Tomorrow", "hi": "कल"}[h.lang]
    return messaging.render("evening_alert", h.lang, day=day, level=level_word(level, h.lang), district=h.district or "",
                            action=action_line(h.lang))
