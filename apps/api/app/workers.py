"""Assisted mode for ASHA, anganwadi and NGO workers (spec §5.3, §5.10, §6.7, §8.4).
- A worker sees and changes only the households they manage; an org_admin can invite workers, deactivate them
  (revoking every session) and reassign households inside their own org. Anything else answers 404.
- Every read and write of a household adds an access_log row.
- People in worker-managed homes are stored with nickname, conditions and medicines encrypted (PERSON_ENC_KEYS).
- Consent: the worker reads a fixed script in the family's language (DRAFT until approved) and records its version.
- The text brief (for WhatsApp/SMS) holds nicknames, place and actions only: no reasons, conditions or medicines."""
import json
from datetime import datetime, timedelta
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from pydantic import Field, StringConstraints
from sqlalchemy import func, select, update
from zoneinfo import ZoneInfo

from engine import people as P
from engine import rules, today, weather

from . import api_v1, config, db, households, http, levels, messaging, notify, secure
from .api_v1 import Problem, Strict
from .models import AccessLog, ConsentEvent, Household, Org, Person, PushTarget, Worker, WorkerSession
from .schemas import Person as PersonIn

router = APIRouter()
LIMIT = http.RateLimiter(120)
IST = ZoneInfo("Asia/Kolkata")
UUID = api_v1.UUID
Name = Annotated[str, StringConstraints(pattern=r"^[\w .'-]{1,60}$")]
BRIEF_ACTIONS = {"go_cooler", "check_on_alone", "extra_care", "fan_not_safe_for_person", "fan_not_enough_for_person", "work_hours_hot",
                 "use_ac_hours", "power_cut_hot", "close_windows", "open_windows"}     # never medicine, fluid or infant lines


# ------------------------------------------------------------------ auth
def worker(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    api_v1._need("TOKEN_PEPPER")
    if not authorization or not authorization.startswith("Bearer "):
        raise Problem(401, "unauthorized", "Missing token")
    th = secure.token_hash(authorization[7:].strip())
    ok, retry = LIMIT.check("w:" + th)
    if not ok:
        raise Problem(429, "rate_limited", "Too many requests", {"Retry-After": str(retry)})
    now = db.utcnow()
    with db.session() as s:
        sess = s.scalars(select(WorkerSession).where(WorkerSession.token_hash == th)).first()
        w = s.get(Worker, sess.worker_id) if sess else None
        if not sess or not secure.same(sess.token_hash, th) or sess.revoked_at or sess.expires_at < now or not w or not w.active:
            http.token_failed(request)
            raise Problem(401, "unauthorized", "Session expired or revoked")
        sess.last_seen_at = w.last_seen_at = now
        return {"id": w.id, "org_id": w.org_id, "role": w.role, "lang": "en"}


def new_session(s, w: Worker) -> str:
    token = secure.new_token()
    life = timedelta(hours=config.ADMIN_SESSION_HOURS) if w.role == "org_admin" else timedelta(days=config.WORKER_SESSION_DAYS)
    s.add(WorkerSession(worker_id=w.id, token_hash=secure.token_hash(token), expires_at=db.utcnow() + life))
    if not s.scalars(select(PushTarget).where(PushTarget.worker_id == w.id, PushTarget.kind == "sms")).first():
        s.add(PushTarget(worker_id=w.id, kind="sms", phone_enc=w.phone_enc, key_id=w.key_id, phone_hmac=w.phone_hmac, verified_via="otp"))
    return token


def _admin(w: dict, org_id: str):
    if w["role"] != "org_admin" or w["org_id"] != org_id:
        raise Problem(404, "not_found", "Not found")


def _owned(s, w: dict, hid: str) -> Household:
    h = s.get(Household, hid)
    if not h or h.managed_by != "worker" or h.worker_id != w["id"] or h.deleted_at:
        raise Problem(404, "not_found", "Not found")            # 404, not 403: other workers' homes aren't confirmed to exist
    return h


def _log(s, w: dict, hid: str, action: str):
    s.add(AccessLog(worker_id=w["id"], household_id=hid, action=action))


# ------------------------------------------------------------------ people at rest
def _store_people(s, h: Household, persons: List[PersonIn]):
    for old in s.scalars(select(Person).where(Person.household_id == h.id)).all():
        s.delete(old)
    for p in persons:
        label = secure.encrypt_field(p.nickname)[0] if p.nickname else None
        cond, kid = secure.encrypt_field(json.dumps(p.conditions))
        meds, _ = secure.encrypt_field(json.dumps(p.medicine_classes))
        s.add(Person(household_id=h.id, label_enc=label, age_band=p.age_band, pregnant=p.pregnant, conditions_enc=cond,
                     medicine_classes_enc=meds, key_id=kid, lives_alone=p.lives_alone, outdoor_work=p.outdoor_work,
                     work_start=p.work_start, work_end=p.work_end, work_type=p.work_type))


def load_people(s, h: Household) -> list[dict]:
    out = []
    for r in s.scalars(select(Person).where(Person.household_id == h.id)).all():
        d = {"age_band": r.age_band, "pregnant": r.pregnant, "lives_alone": r.lives_alone, "outdoor_work": r.outdoor_work,
             "conditions": json.loads(secure.decrypt_field(r.conditions_enc, r.key_id)) if r.conditions_enc else [],
             "medicine_classes": json.loads(secure.decrypt_field(r.medicine_classes_enc, r.key_id)) if r.medicine_classes_enc else []}
        if r.label_enc:
            d["nickname"] = secure.decrypt_field(r.label_enc, r.key_id)
        for k in ("work_start", "work_end", "work_type"):
            if getattr(r, k):
                d[k] = getattr(r, k)
        out.append(d)
    return out


# ------------------------------------------------------------------ the day for one home
def assess(h: Household, persons: list[dict], day: str, lang: str) -> dict:
    """Level, people at higher risk and the actions for one worker-managed home on 'today' or 'tomorrow'."""
    w = weather.fetch(h.cell_lat, h.cell_lon)
    first = datetime.now(IST).date()
    date_s = (first + timedelta(days=1 if day == "tomorrow" else 0)).isoformat()
    lv = levels.day_level(w, date_s, h.cell_lat, h.cell_lon, h.district_id, h.in_delhi, day) or {"level": "low", "level_index": 0, "reasons": []}
    rows = levels.day_rows(w, date_s)
    hottest = sorted(sorted(rows, key=lambda r: max(r["hi"], r["t"]), reverse=True)[:3], key=lambda r: r["time"])
    devices = {"fan": bool(h.fan), "cooler": bool(h.cooler), "ac": bool(h.ac)}
    adv = today.build(persons, [], rows, {"hottest": [r["time"][11:16] for r in hottest]}, lv["level_index"], devices,
                      [list(x) for x in (h.power_cut_hours or [])], lang)
    at_risk = [{"person": pp["person"], "label": pp["label"], "age_band": persons[pp["person"]]["age_band"], "why": pp["reasons"]}
               for pp in adv["per_person"] if pp["higher_risk_today"]]
    return {"household_id": h.id, "district": h.district, "ward_no": h.ward_no, "date": date_s, "level": lv["level"],
            "level_index": lv["level_index"], "persons_at_risk": at_risk, "actions": adv["today_actions"]}


# ------------------------------------------------------------------ org admin
class Invite(Strict):
    display_name: Name
    phone: api_v1.Phone
    role: Literal["asha", "anganwadi", "ngo", "volunteer"]


class WorkerPatch(Strict):
    active: bool


class Reassign(Strict):
    worker_id: Annotated[str, StringConstraints(pattern=UUID)]


@router.post("/api/v1/orgs/{org_id}/workers", status_code=201)
def invite(q: Invite, org_id: Annotated[str, Path(pattern=UUID)], w: dict = Depends(worker)):
    _admin(w, org_id)
    phone = api_v1._phone(q.phone)
    ph = secure.phone_hmac(phone)
    with db.session() as s:
        if s.scalars(select(Worker).where(Worker.phone_hmac == ph)).first():
            raise Problem(409, "exists", "This number is already a worker")
        org = s.get(Org, org_id)
        enc, kid = secure.encrypt_phone(phone)
        nw = Worker(org_id=org_id, role=q.role, display_name=q.display_name, phone_enc=enc, key_id=kid, phone_hmac=ph,
                    district_id=org.district_id if org else None)
        s.add(nw)
        s.flush()
        return {"worker_id": nw.id, "role": nw.role}


@router.patch("/api/v1/orgs/{org_id}/workers/{worker_id}")
def set_active(q: WorkerPatch, org_id: Annotated[str, Path(pattern=UUID)], worker_id: Annotated[str, Path(pattern=UUID)], w: dict = Depends(worker)):
    _admin(w, org_id)
    with db.session() as s:
        t = s.get(Worker, worker_id)
        if not t or t.org_id != org_id:
            raise Problem(404, "not_found", "Not found")
        t.active = q.active
        if not q.active:                                           # deactivating revokes every session (spec §5.10)
            s.execute(update(WorkerSession).where(WorkerSession.worker_id == worker_id, WorkerSession.revoked_at.is_(None))
                      .values(revoked_at=db.utcnow()))
        return {"worker_id": t.id, "active": t.active}


@router.patch("/api/v1/orgs/{org_id}/households/{hid}")
def reassign(q: Reassign, org_id: Annotated[str, Path(pattern=UUID)], hid: Annotated[str, Path(pattern=UUID)], w: dict = Depends(worker)):
    _admin(w, org_id)
    with db.session() as s:
        h = s.get(Household, hid)
        old = s.get(Worker, h.worker_id) if h and h.worker_id else None
        new = s.get(Worker, q.worker_id)
        if not h or not old or old.org_id != org_id or not new or new.org_id != org_id or not new.active:
            raise Problem(404, "not_found", "Not found")
        h.worker_id = new.id
        _log(s, w, hid, "edit")
        return {"household_id": hid, "worker_id": new.id}


# ------------------------------------------------------------------ worker
class WorkerConsent(Strict):
    version: Annotated[str, StringConstraints(max_length=20)]
    by: Literal["worker"]
    script_version: Annotated[str, StringConstraints(max_length=20)]


class WorkerHouseholdIn(Strict):
    consent: WorkerConsent
    lang: Literal["en", "hi"] = "en"
    place: households.Place
    home: households.Home = households.Home()
    people: List[PersonIn] = Field(..., min_length=1, max_length=20)


class WorkerHouseholdPatch(Strict):
    lang: Optional[Literal["en", "hi"]] = None
    place: Optional[households.Place] = None
    home: Optional[households.Home] = None
    people: Optional[List[PersonIn]] = Field(default=None, min_length=1, max_length=20)


@router.get("/api/v1/workers/me")
def me(w: dict = Depends(worker)):
    with db.session() as s:
        wk, org = s.get(Worker, w["id"]), s.get(Org, w["org_id"])
        n = s.scalar(select(func.count()).select_from(Household).where(Household.worker_id == w["id"], Household.deleted_at.is_(None))) or 0
        return {"worker_id": wk.id, "display_name": wk.display_name, "role": wk.role, "org": {"id": org.id, "name": org.name, "type": org.type} if org else None,
                "district_id": wk.district_id, "households": n}


@router.get("/api/v1/workers/me/households")
def my_households(day: Literal["today", "tomorrow"] = "today", min_level: Literal["low", "moderate", "high", "extreme"] = "low",
                  lang: Literal["en", "hi"] = "en", w: dict = Depends(worker)):
    out = []
    with db.session() as s:
        homes = s.scalars(select(Household).where(Household.worker_id == w["id"], Household.managed_by == "worker", Household.deleted_at.is_(None))).all()
        for h in homes:
            a = assess(h, load_people(s, h), day, lang)
            _log(s, w, h.id, "view")
            if a["level_index"] >= rules.LEVELS.index(min_level):
                out.append({**a, "top_actions": a.pop("actions")[:4]})
    out.sort(key=lambda r: (-r["level_index"], -len(r["persons_at_risk"])))
    return {"day": day, "households": out}


@router.post("/api/v1/workers/me/households", status_code=201)
def add_household(q: WorkerHouseholdIn, w: dict = Depends(worker)):
    if q.consent.script_version != config.CONSENT_SCRIPT_VERSION or q.consent.version != config.CONSENT_VERSION_APP:
        raise Problem(409, "consent_outdated", "Please read the latest consent script")
    with db.session() as s:
        h = Household(lang=q.lang, managed_by="worker", worker_id=w["id"], consent_version=q.consent.version, consent_at=db.utcnow(), consent_by="worker")
        households._place(h, q.place)
        households._apply(h, q.home, None, None)
        h.higher_risk = any(today.CARE & set(P.care_reasons(p.model_dump())) for p in q.people)
        s.add(h)
        s.flush()
        _store_people(s, h, q.people)
        s.add(ConsentEvent(household_id=h.id, worker_id=w["id"], action="given", consent_version=q.consent.version, by="worker"))
        _log(s, w, h.id, "create")
        return {"household_id": h.id}


@router.patch("/api/v1/workers/me/households/{hid}")
def edit_household(q: WorkerHouseholdPatch, hid: Annotated[str, Path(pattern=UUID)], w: dict = Depends(worker)):
    with db.session() as s:
        h = _owned(s, w, hid)
        if q.lang:
            h.lang = q.lang
        if q.place:
            households._place(h, q.place)
        if q.home:
            households._apply(h, q.home, None, None, fields=q.home.model_fields_set)
        if q.people is not None:
            _store_people(s, h, q.people)
            h.higher_risk = any(today.CARE & set(P.care_reasons(p.model_dump())) for p in q.people)
        _log(s, w, hid, "edit")
        return {"household_id": hid, "people": len(load_people(s, h))}


@router.delete("/api/v1/workers/me/households/{hid}", status_code=204)
def delete_household(hid: Annotated[str, Path(pattern=UUID)], w: dict = Depends(worker)):
    with db.session() as s:
        h = _owned(s, w, hid)
        s.add(ConsentEvent(household_id=hid, worker_id=w["id"], action="deleted", consent_version=h.consent_version, by="worker"))
        _log(s, w, hid, "delete")
        s.delete(h)                                                # people go with it (cascade)
    return Response(status_code=204)


def brief_text(rows: list[dict], day: str, lang: str, use_roles: bool = False) -> str:
    """For WhatsApp/SMS: nicknames, place and actions only (spec §6.7); checked for health words (spec §2 rule 7).
    If a nickname itself holds a health word, the brief is rebuilt with role names ("The older person") instead."""
    head = messaging.render("worker_brief_head", lang, day={"today": {"en": "Today", "hi": "आज"}, "tomorrow": {"en": "Tomorrow", "hi": "कल"}}[day][lang],
                            count=len(rows))
    lines = []
    for i, r in enumerate(rows, 1):
        swap = {p["label"]: today._t("roles", P.role({"age_band": p["age_band"]}), lang) for p in r["persons_at_risk"]} if use_roles else {}
        names = ", ".join(swap.get(p["label"], p["label"]) for p in r["persons_at_risk"]) or "—"
        place = r["district"] or ""
        if r.get("ward_no"):
            place += f" {'वार्ड' if lang == 'hi' else 'ward'} {r['ward_no']}"
        acts: list[str] = []
        for a in r["actions"]:
            if a["code"] in BRIEF_ACTIONS and len(acts) < 2:
                text = a["text"]
                for nick, role in swap.items():
                    text = text.replace(nick, role)
                acts.append(text)
        lines.append(f"{i}. {names} ({place}): " + " ".join(acts))
    try:
        return notify.no_health(head + "\n" + "\n".join(lines))
    except ValueError:
        if use_roles:
            raise
        return brief_text(rows, day, lang, use_roles=True)


@router.get("/api/v1/workers/me/brief")
def brief(day: Literal["today", "tomorrow"] = "tomorrow", format: Literal["json", "text"] = "json", lang: Literal["en", "hi"] = "en",
          w: dict = Depends(worker)):
    rows = []
    with db.session() as s:
        for h in s.scalars(select(Household).where(Household.worker_id == w["id"], Household.managed_by == "worker", Household.deleted_at.is_(None))).all():
            a = assess(h, load_people(s, h), day, lang)
            _log(s, w, h.id, "brief")
            if a["persons_at_risk"] or a["level_index"] >= 2:
                rows.append(a)
    rows.sort(key=lambda r: (-r["level_index"], -len(r["persons_at_risk"])))
    if format == "text":
        return {"text": brief_text(rows, day, lang)}
    return {"day": day, "households": [{**{k: r[k] for k in ("household_id", "district", "ward_no", "level", "persons_at_risk")},
                                        "actions": r["actions"]} for r in rows]}
