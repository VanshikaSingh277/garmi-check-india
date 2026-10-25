"""Saved households (spec §6.3). Off unless HOUSEHOLDS_ENABLED=true: the frontend prerequisite in spec §6.3
(escape-by-default templating + a CSP on the website; the token in Keychain/Keystore in the app) must be done first.
- The token is 32 random bytes, shown once; only its peppered hash is stored. Rotate and delete in one call.
- Stored per spec §5.1: the 0.1 deg cell (never the exact GPS), home settings, the higher_risk flag, counts only when
  share_counts is ticked. People stay on the phone and come with each status / outlook request.
- Export shows phone numbers masked: they are decrypted only to send (spec §8.3)."""
from datetime import datetime
from typing import Annotated, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, StringConstraints
from sqlalchemy import func, select

from engine import areas, districts

from . import api_v1, config, db, http, secure
from .api_v1 import Problem, Strict
from .models import ConsentEvent, Household, NoticeLog, PushTarget

router = APIRouter()
NEW_LIMIT = http.RateLimiter(config.HOUSEHOLDS_PER_IP_HOUR, 3600)
Clock = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Level = Literal["high", "extreme"]


def enabled():
    if not config.HOUSEHOLDS_ENABLED:
        raise Problem(404, "not_enabled", "Saved homes aren't switched on yet")


class Consent(Strict):
    version: Annotated[str, StringConstraints(max_length=20)]
    accepted: Literal[True]


class Place(Strict):
    lat: float = Field(..., ge=6.5, le=37.5)
    lon: float = Field(..., ge=68.0, le=97.5)


class Home(Strict):
    roof: Optional[Literal["tin_top", "asbestos_top", "stone_slab_top", "rcc_brick_top", "lower_floor"]] = None
    roof_access: Optional[bool] = None
    cross_ventilation: Optional[bool] = None
    budget: Optional[Literal["free", "low", "medium", "high"]] = None
    tenure: Optional[Literal["own", "rent", "other"]] = None
    floor_level: Optional[int] = Field(default=None, ge=0, le=60)
    fan: Optional[bool] = None
    cooler: Optional[bool] = None
    ac: Optional[bool] = None
    power_cuts: Optional[bool] = None
    power_cut_hours: List[Tuple[Clock, Clock]] = Field(default=[], max_length=6)
    water_short: Optional[bool] = None


class Counts(Strict):
    older: int = Field(default=0, ge=0, le=20)
    infant: int = Field(default=0, ge=0, le=20)
    child: int = Field(default=0, ge=0, le=20)
    pregnant: int = Field(default=0, ge=0, le=20)
    outdoor_worker: int = Field(default=0, ge=0, le=20)


class Summary(Strict):
    higher_risk: bool = False
    outdoor_work_window: Optional[Tuple[Clock, Clock]] = None
    share_counts: bool = False
    counts: Optional[Counts] = None


class Alerts(Strict):
    enabled: bool = False
    hour_ist: int = Field(default=19, ge=18, le=21)
    min_level: Level = "high"


class HouseholdIn(Strict):
    consent: Consent
    lang: Literal["en", "hi"] = "en"
    place: Place
    home: Home = Home()
    summary: Summary = Summary()
    alerts: Alerts = Alerts()


class HouseholdPatch(Strict):
    lang: Optional[Literal["en", "hi"]] = None
    place: Optional[Place] = None
    home: Optional[Home] = None
    summary: Optional[Summary] = None
    alerts: Optional[Alerts] = None


def _place(h: Household, p: Place):
    d = districts.district_at(p.lat, p.lon)
    if not d:
        raise Problem(422, "outside_india", "This place is outside India")
    w = areas.ward_at(p.lat, p.lon) if 28.40 <= p.lat <= 28.89 and 76.83 <= p.lon <= 77.35 else None
    h.cell_lat, h.cell_lon = round(p.lat, 1), round(p.lon, 1)
    h.district_id, h.district, h.state = d["id"], d["district"], d.get("state")
    h.in_delhi, h.ward_no = bool(w), (str(w["ward_no"]) if w else None)


def _apply(h: Household, home: Home | None, summary: Summary | None, alerts: Alerts | None, fields: set | None = None):
    if home is not None:
        for k, v in home.model_dump().items():
            if fields is None or k in fields:
                setattr(h, k, v)
    if summary is not None:
        h.higher_risk = summary.higher_risk
        h.outdoor_work_window = list(summary.outdoor_work_window) if summary.outdoor_work_window else None
        h.share_counts = summary.share_counts
        h.counts = summary.counts.model_dump() if (summary.share_counts and summary.counts) else None   # only when shared
    if alerts is not None:
        h.alerts_enabled, h.alert_hour_ist, h.alert_min_level = alerts.enabled, alerts.hour_ist, alerts.min_level


def public(h: Household, s) -> dict:
    targets = s.scalars(select(PushTarget).where(PushTarget.household_id == h.id)).all()
    return {"household_id": h.id, "lang": h.lang, "cell": {"lat": h.cell_lat, "lon": h.cell_lon}, "district": h.district, "state": h.state,
            "ward_no": h.ward_no,
            "home": {k: getattr(h, k) for k in Home.model_fields},
            "summary": {"higher_risk": h.higher_risk, "outdoor_work_window": h.outdoor_work_window, "share_counts": h.share_counts, "counts": h.counts},
            "alerts": {"enabled": h.alerts_enabled, "hour_ist": h.alert_hour_ist, "min_level": h.alert_min_level},
            "push": [{"id": t.id, "kind": t.kind, "active": t.active, "phone": ("…" + secure.decrypt_phone(t.phone_enc, t.key_id)[-2:]) if t.phone_enc else None}
                     for t in targets],
            "consent": {"version": h.consent_version, "at": h.consent_at.isoformat() if h.consent_at else None, "by": h.consent_by},
            "created_at": h.created_at.isoformat(), "last_seen_at": h.last_seen_at.isoformat()}


@router.post("/api/v1/households", status_code=201, dependencies=[Depends(enabled)])
def create(q: HouseholdIn, request: Request):
    api_v1._need("TOKEN_PEPPER")
    ok, retry = NEW_LIMIT.check("ip:" + http.client_ip(request.scope))
    if not ok:
        raise Problem(429, "rate_limited", "Too many new homes from here", {"Retry-After": str(retry)})
    if q.consent.version != config.CONSENT_VERSION_APP:
        raise Problem(409, "consent_outdated", "Please read the latest notice")
    token = secure.new_token()
    with db.session() as s:
        today = s.scalar(select(func.count()).select_from(Household).where(Household.created_at >= datetime.combine(db.utcnow().date(), datetime.min.time()))) or 0
        if today >= config.HOUSEHOLDS_DAILY_CAP:
            raise Problem(503, "daily_cap", "Please try again tomorrow")
        h = Household(token_hash=secure.token_hash(token), token_created_at=db.utcnow(), lang=q.lang, managed_by="self",
                      consent_version=q.consent.version, consent_at=db.utcnow(), consent_by="self")
        _place(h, q.place)
        _apply(h, q.home, q.summary, q.alerts)
        s.add(h)
        s.flush()
        s.add(ConsentEvent(household_id=h.id, action="given", consent_version=h.consent_version, by="self"))
        return {"household_id": h.id, "token": token}


@router.get("/api/v1/households/me", dependencies=[Depends(enabled)])
def me(hid: str = Depends(api_v1.household)):
    with db.session() as s:
        return public(s.get(Household, hid), s)


@router.patch("/api/v1/households/me", dependencies=[Depends(enabled)])
def update(q: HouseholdPatch, hid: str = Depends(api_v1.household)):
    with db.session() as s:
        h = s.get(Household, hid)
        if q.lang:
            h.lang = q.lang
        if q.place:
            _place(h, q.place)
        _apply(h, q.home, q.summary, q.alerts, fields=q.home.model_fields_set if q.home else None)
        s.flush()
        return public(h, s)


@router.delete("/api/v1/households/me", status_code=204, dependencies=[Depends(enabled)])
def delete(hid: str = Depends(api_v1.household)):
    with db.session() as s:
        h = s.get(Household, hid)
        s.add(ConsentEvent(household_id=hid, action="deleted", consent_version=h.consent_version, by="self"))
        s.delete(h)                                   # push targets go with it (cascade); notices are deleted below
        for n in s.scalars(select(NoticeLog).where(NoticeLog.recipient_key == f"h:{hid}")).all():
            s.delete(n)
    return Response(status_code=204)


@router.get("/api/v1/households/me/export", dependencies=[Depends(enabled)])
def export(hid: str = Depends(api_v1.household)):
    with db.session() as s:
        h = s.get(Household, hid)
        notices = s.scalars(select(NoticeLog).where(NoticeLog.recipient_key == f"h:{hid}")).all()
        consents = s.scalars(select(ConsentEvent).where(ConsentEvent.household_id == hid)).all()
        s.add(ConsentEvent(household_id=hid, action="exported", consent_version=h.consent_version, by="self"))
        return {"household": public(h, s),
                "notices": [{"for_date": n.for_date.isoformat(), "kind": n.kind, "channel": n.channel, "level": n.level, "status": n.status,
                             "text": n.text} for n in notices],
                "consent_events": [{"action": c.action, "version": c.consent_version, "by": c.by, "at": c.at.isoformat()} for c in consents],
                "note": "Phone numbers are shown masked: they are stored encrypted and only decrypted to send your alerts."}


@router.post("/api/v1/households/me/token/rotate", dependencies=[Depends(enabled)])
def rotate(hid: str = Depends(api_v1.household)):
    token = secure.new_token()
    with db.session() as s:
        h = s.get(Household, hid)
        h.token_hash, h.token_created_at = secure.token_hash(token), db.utcnow()
    return {"token": token}


def stored_answers(h: Household) -> dict:
    """The saved home as /api/status/individual answers (people come from the phone)."""
    return {"lat": h.cell_lat, "lon": h.cell_lon, "roof": h.roof or "rcc_brick_top", "roof_access": bool(h.roof_access) if h.roof_access is not None else True,
            "cross_ventilation": h.cross_ventilation, "budget": h.budget, "lang": h.lang, "tenure": h.tenure,
            "devices": {"fan": bool(h.fan), "cooler": bool(h.cooler), "ac": bool(h.ac)}, "power_cuts": h.power_cuts,
            "power_cut_hours": [list(x) for x in (h.power_cut_hours or [])], "water_short": h.water_short}

