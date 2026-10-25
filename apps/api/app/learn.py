"""Readings, feedback and fix progress for saved homes (spec §5.6-5.8, §6.4, §7.4). Behind HOUSEHOLDS_ENABLED.
- A reading is 10-55 C (else 422). The server adds the outdoor air and the model's estimate for that hour from the
  cached forecast, with the home's saved roof, fan and cooler. Kitchen readings, and hours outside the model's
  training range, are kept but never used for calibration. From 5 readings on, odd ones are flagged, not dropped.
- Feedback: one answer a day, no free text, kept 90 days; anyone_unwell is not a medical record.
- Fix progress: the measured effect uses the same before/after method as the app (solutions.estimate_fix_effect)."""
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import Field, StringConstraints
from sqlalchemy import select
from zoneinfo import ZoneInfo

from engine import indoor, solutions, weather

from . import api_v1, calibrate, config, db, households
from .api_v1 import Problem, Strict
from .models import FixProgress, Household, Reading
from .models import Feedback as FeedbackRow

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
MODEL_ROOF = {"asbestos_top": "tin_top"}


class ReadingIn(Strict):
    ts: Optional[datetime] = None                    # IST; defaults to now; rounded to the hour
    room: Literal["bedroom", "living", "kitchen", "other"]
    indoor_c: float = Field(..., ge=config.READING_MIN_C, le=config.READING_MAX_C)
    source: Literal["thermometer", "ac_remote", "logger", "other"] = "thermometer"
    fix_id: Optional[Annotated[str, StringConstraints(pattern=r"^[a-z_]{3,40}$")]] = None


class FeedbackIn(Strict):
    for_date: date
    night_feel: Literal["fine", "hot", "could_not_sleep"]
    followed_plan: Optional[Literal["yes", "partly", "no"]] = None
    anyone_unwell: Optional[bool] = None


class FixIn(Strict):
    status: Literal["planned", "done", "not_possible"]
    done_at: Optional[date] = None


def _hour(ts: datetime | None) -> datetime:
    now = datetime.now(IST).replace(tzinfo=None)
    t = (ts.astimezone(IST).replace(tzinfo=None) if ts and ts.tzinfo else ts) or now
    if t > now + timedelta(minutes=5) or t < now - timedelta(days=2):
        raise Problem(422, "invalid_input", "A reading must be from the last 2 days")
    return t.replace(minute=0, second=0, microsecond=0)


def _model_hour(h: Household, hour: datetime) -> tuple[float | None, float | None]:
    """(outdoor_c, predicted_c) for that hour from the cached forecast; predicted only inside the training range."""
    w = weather.fetch(h.cell_lat, h.cell_lon)
    key = hour.strftime("%Y-%m-%dT%H:00")
    k = next((i for i, r in enumerate(w["hourly"]) if r["time"] == key), None)
    if k is None:
        return None, None
    row = w["hourly"][k]
    a = indoor._model()[1]["applicability"]
    inside = a["t_c"][0] <= row["t"] <= a["t_c"][1] and a["rh_pct"][0] <= row["rh"] <= a["rh_pct"][1]
    if not inside or k < 24 or not h.roof:
        return row["t"], None
    p = indoor.predict(w["hourly"], k, MODEL_ROOF.get(h.roof, h.roof), bool(h.fan), bool(h.cooler), hours=1)
    return row["t"], (p[0]["indoor"] if p else None)


def _out(r: Reading) -> dict:
    return {"id": r.id, "ts": r.ts.isoformat(timespec="minutes"), "room": r.room, "indoor_c": r.indoor_c, "outdoor_c": r.outdoor_c,
            "predicted_c": r.predicted_c, "source": r.source, "period": r.period, "used_for_calibration": r.used_for_calibration,
            "outlier": r.outlier, "fix_id": r.fix_id}


@router.post("/api/v1/households/me/readings", status_code=201, dependencies=[Depends(households.enabled)])
def add_reading(q: ReadingIn, hid: str = Depends(api_v1.household)):
    if q.fix_id and q.fix_id not in {f["id"] for f in solutions.catalogue()["fixes"]}:
        raise Problem(422, "invalid_input", "Unknown fix")
    hour = _hour(q.ts)
    with db.session() as s:
        h = s.get(Household, hid)
        outdoor_c, predicted = _model_hour(h, hour)
        per = calibrate.period(hour.hour)
        r = Reading(household_id=hid, ts=hour, room=q.room, indoor_c=q.indoor_c, outdoor_c=outdoor_c, predicted_c=predicted,
                    source=q.source, period=per, fix_id=q.fix_id)
        if predicted is not None and q.room != "kitchen":
            others = [x.indoor_c - x.predicted_c for x in s.scalars(select(Reading).where(
                Reading.household_id == hid, Reading.used_for_calibration.is_(True), Reading.period == per)).all() if x.predicted_c is not None]
            r.outlier = calibrate.outlier(q.indoor_c - predicted, others)
            r.used_for_calibration = not r.outlier
        s.add(r)
        s.flush()
        return {"reading": _out(r), "calibration": calibrate.recompute(s, h)}


@router.get("/api/v1/households/me/readings", dependencies=[Depends(households.enabled)])
def list_readings(from_: Optional[date] = Query(None, alias="from"), to: Optional[date] = None, hid: str = Depends(api_v1.household)):
    with db.session() as s:
        q = select(Reading).where(Reading.household_id == hid)
        if from_:
            q = q.where(Reading.ts >= datetime.combine(from_, datetime.min.time()))
        if to:
            q = q.where(Reading.ts < datetime.combine(to + timedelta(days=1), datetime.min.time()))
        return {"readings": [_out(r) for r in s.scalars(q.order_by(Reading.ts)).all()]}


@router.delete("/api/v1/households/me/readings/{reading_id}", status_code=204, dependencies=[Depends(households.enabled)])
def delete_reading(reading_id: Annotated[str, Path(pattern=api_v1.UUID)], hid: str = Depends(api_v1.household)):
    with db.session() as s:
        r = s.get(Reading, reading_id)
        if not r or r.household_id != hid:
            raise Problem(404, "not_found", "Not found")
        s.delete(r)
        s.flush()
        calibrate.recompute(s, s.get(Household, hid))
    return Response(status_code=204)


@router.post("/api/v1/households/me/feedback", status_code=204, dependencies=[Depends(households.enabled)])
def feedback(q: FeedbackIn, hid: str = Depends(api_v1.household)):
    if not (date.today() - timedelta(days=7) <= q.for_date <= date.today() + timedelta(days=1)):
        raise Problem(422, "invalid_input", "Feedback is for the last week only")
    with db.session() as s:
        s.merge(FeedbackRow(household_id=hid, for_date=q.for_date, night_feel=q.night_feel, followed_plan=q.followed_plan, anyone_unwell=q.anyone_unwell))
    return Response(status_code=204)


def fix_effect(s, hid: str, fix_id: str, done_at: date | None) -> dict:
    if not done_at:
        return {"status": "need_more_readings", "have": {"before": 0, "after": 0}}
    rows = s.scalars(select(Reading).where(Reading.household_id == hid, Reading.outdoor_c.is_not(None), Reading.room != "kitchen")).all()
    before = [{"indoor_c": r.indoor_c, "outdoor_c": r.outdoor_c} for r in rows if r.ts.date() < done_at]
    after = [{"indoor_c": r.indoor_c, "outdoor_c": r.outdoor_c} for r in rows if r.ts.date() >= done_at and (r.fix_id in (None, fix_id))]
    return solutions.estimate_fix_effect(before, after)


@router.put("/api/v1/households/me/fixes/{fix_id}", dependencies=[Depends(households.enabled)])
def set_fix(q: FixIn, fix_id: Annotated[str, Path(pattern=r"^[a-z_]{3,40}$")], hid: str = Depends(api_v1.household)):
    if fix_id not in {f["id"] for f in solutions.catalogue()["fixes"]}:
        raise Problem(404, "not_found", "Unknown fix")
    with db.session() as s:
        row = s.get(FixProgress, (hid, fix_id)) or FixProgress(household_id=hid, fix_id=fix_id)
        row.status = q.status
        row.done_at = q.done_at if q.status == "done" else None
        eff: dict = fix_effect(s, hid, fix_id, row.done_at) if q.status == "done" else {"status": "not_done"}
        row.measured_effect_c = eff.get("effect_c")
        row.measured_n = (eff["days"]["before"] + eff["days"]["after"]) if eff.get("status") == "ok" else None
        s.merge(row)
        return {"fix_id": fix_id, "status": row.status, "done_at": row.done_at.isoformat() if row.done_at else None,
                "measured_effect_c": row.measured_effect_c, "measured": eff}


def progress(s, hid: str) -> list[dict]:
    return [{"fix_id": p.fix_id, "status": p.status, "done_at": p.done_at.isoformat() if p.done_at else None,
             "measured_effect_c": p.measured_effect_c, "measured_n": p.measured_n}
            for p in s.scalars(select(FixProgress).where(FixProgress.household_id == hid)).all()]
