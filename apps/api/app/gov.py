"""Anonymous numbers for government (spec §5.11, §6.8). Built from homes that ticked "share anonymous counts" plus
worker-managed homes. Any count below AGG_MIN_COUNT is stored as NULL, so no single home can be picked out, and every
answer says these are "among Thandak users", not the whole population."""
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from zoneinfo import ZoneInfo

from engine import weather

from . import config, db, levels
from .schemas import Problem
from .models import DailyAggregate, Feedback, Household, ImdWarning, NoticeLog, Person

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
NOTE = "Among Thandak users only (homes that chose to share anonymous counts, and homes registered by health workers). Not the whole population."
FIELDS = ("households", "households_high", "households_extreme", "people_older", "people_infant", "people_pregnant",
          "people_outdoor_work", "alerts_sent", "alerts_opened", "nights_could_not_sleep")


def _small(n: int) -> int | None:
    return n if n >= config.AGG_MIN_COUNT else None


def build(day: date | None = None) -> dict:
    """23:30: one row per district for the day. Levels come from each home's 0.1 deg cell (cached forecast)."""
    day = day or datetime.now(IST).date()
    level_cache: dict = {}
    per: dict = {}
    with db.session() as s:
        homes = s.scalars(select(Household).where(Household.deleted_at.is_(None), Household.district_id.is_not(None),
                                                  (Household.share_counts.is_(True)) | (Household.managed_by == "worker"))).all()
        for h in homes:
            key = (h.cell_lat, h.cell_lon)
            if key not in level_cache:
                try:
                    w = weather.fetch(*key)
                    lv = levels.day_level(w, day.isoformat(), h.cell_lat, h.cell_lon, h.district_id, h.in_delhi, "today")
                    level_cache[key] = lv["level_index"] if lv else 0
                except weather.WeatherUnavailable:
                    level_cache[key] = None
            lvl = level_cache[key]
            d = per.setdefault(h.district_id, dict.fromkeys(FIELDS, 0))
            d["households"] += 1
            hot = lvl is not None and lvl >= 2
            d["households_high"] += lvl == 2
            d["households_extreme"] += lvl == 3
            if hot:
                if h.managed_by == "worker":
                    ps = s.scalars(select(Person).where(Person.household_id == h.id)).all()
                    d["people_older"] += sum(p.age_band.startswith("older") for p in ps)
                    d["people_infant"] += sum(p.age_band == "infant_0_1" for p in ps)
                    d["people_pregnant"] += sum(bool(p.pregnant) for p in ps)
                    d["people_outdoor_work"] += sum(bool(p.outdoor_work) for p in ps)
                elif h.counts:
                    d["people_older"] += int(h.counts.get("older", 0))
                    d["people_infant"] += int(h.counts.get("infant", 0))
                    d["people_pregnant"] += int(h.counts.get("pregnant", 0))
                    d["people_outdoor_work"] += int(h.counts.get("outdoor_worker", 0))
            sent = s.scalars(select(NoticeLog.status).where(NoticeLog.recipient_key == f"h:{h.id}", NoticeLog.for_date == day)).all()
            d["alerts_sent"] += sum(x in ("sent", "opened") for x in sent)
            d["alerts_opened"] += sum(x == "opened" for x in sent)
            d["nights_could_not_sleep"] += s.scalar(select(func.count()).select_from(Feedback).where(
                Feedback.household_id == h.id, Feedback.for_date == day, Feedback.night_feel == "could_not_sleep")) or 0
        for did, d in per.items():
            s.merge(DailyAggregate(for_date=day, district_id=did, **{k: _small(v) for k, v in d.items()}))
    return {"date": day.isoformat(), "districts": len(per)}


def _row(a: DailyAggregate, imd: str | None) -> dict:
    return {"date": a.for_date.isoformat(), "district_id": a.district_id, **{k: getattr(a, k) for k in FIELDS}, "imd_color": imd}


@router.get("/api/v1/gov/today")
def today(district_id: Optional[str] = Query(None, max_length=40), day: Optional[date] = None,
          state: Optional[str] = Query(None, max_length=60)):
    day = day or datetime.now(IST).date()
    from engine import districts
    with db.session() as s:
        q = select(DailyAggregate).where(DailyAggregate.for_date == day)
        if district_id:
            q = q.where(DailyAggregate.district_id == district_id)
        rows = s.scalars(q).all()
        imd = {w.district_id: w.color for w in s.scalars(select(ImdWarning).where(ImdWarning.for_date == day)).all()}
    out = [_row(a, imd.get(a.district_id)) for a in rows]
    if state:
        ids = {d["id"] for d in districts.ranking(state, 1000)["districts"]}
        out = [r for r in out if r["district_id"] in ids]
    return {"date": day.isoformat(), "note": NOTE, "min_count": config.AGG_MIN_COUNT, "rows": out}


@router.get("/api/v1/gov/trend")
def trend(district_id: str = Query(..., max_length=40), from_: date = Query(..., alias="from"), to: date = Query(...),
          kind: Literal["daily"] = "daily"):
    if to < from_ or (to - from_) > timedelta(days=366):
        raise Problem(422, "invalid_input", "Choose up to one year")
    with db.session() as s:
        rows = s.scalars(select(DailyAggregate).where(DailyAggregate.district_id == district_id, DailyAggregate.for_date >= from_,
                                                      DailyAggregate.for_date <= to).order_by(DailyAggregate.for_date)).all()
        imd = {(w.for_date): w.color for w in s.scalars(select(ImdWarning).where(ImdWarning.district_id == district_id,
                                                                                    ImdWarning.for_date >= from_, ImdWarning.for_date <= to)).all()}
    return {"district_id": district_id, "note": NOTE, "min_count": config.AGG_MIN_COUNT, "rows": [_row(a, imd.get(a.for_date)) for a in rows]}
