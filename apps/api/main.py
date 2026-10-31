"""Thandak - heat-risk API + static frontend (one service). Works for any point in India;
Delhi additionally gets ward-level detail. Backend spec: docs/BACKEND_SPEC.md.
Run locally:  python run_local.py "" 8000   (from apps/api)
"""
import csv
import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, List, Literal, Optional, Tuple, Union
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import api_v1, calibrate, config, db, gov, households, http, imd, learn, levels, manifest, notify, observe, secure, workers
from app.schemas import Person
from engine import areas, districts, indoor, normals, people, places, plan, rules, scenario, solutions, today, weather
from engine import verified as V

API_VERSION = "0.3.0"
HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
# the built frontend (npm run build in apps/web); the Docker image copies it to ../web
WEB = next((p for p in (os.path.join(HERE, "..", "web", "dist"), os.path.join(HERE, "..", "web")) if os.path.isfile(os.path.join(p, "index.html"))), None)
IST = ZoneInfo("Asia/Kolkata")
DELHI_BBOX = (28.40, 76.83, 28.89, 77.35)
# India bounds (spec §6.1); a point must also fall inside the district polygons
LAT = dict(ge=6.5, le=37.5)
LON = dict(ge=68.0, le=97.5)
Roof = Literal["tin_top", "asbestos_top", "stone_slab_top", "rcc_brick_top", "lower_floor"]
Vulnerable = Literal["elderly", "child", "pregnant", "chronic", "outdoor_worker"]
Lang = Literal["en", "hi"]
Clock = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
# the room model learned from four roof groups; an asbestos-cement sheet roof behaves like tin (thin sheet, no thermal mass)
MODEL_ROOF = {"asbestos_top": "tin_top"}
# questionnaire roof answer -> the fix catalogue's roof type and floor
ROOF_TYPE = {"tin_top": "tin", "asbestos_top": "asbestos", "stone_slab_top": "stone_slab", "rcc_brick_top": "concrete"}
HEADLINE_SWITCH_H = 18          # spec §7.1: today's level before 18:00 IST, tomorrow's after


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@asynccontextmanager
async def lifespan(_app):
    manifest.verify(config.PROD)    # prod refuses to start when a data file doesn't match data/MANIFEST.json
    if config.PROD and (bad := secure.prod_problems()):
        raise RuntimeError("refusing to start: " + "; ".join(bad))
    observe.init_sentry()
    db.migrate()                    # alembic upgrade head (safe to repeat)
    places.warm()                   # ~2 s: load the offline gazetteer once, not on the first user's request
    yield


api = FastAPI(title="Thandak API", version=API_VERSION, lifespan=lifespan,
              docs_url="/docs" if config.DOCS_ENABLED else None, redoc_url=None,
              openapi_url="/openapi.json" if config.DOCS_ENABLED else None)
api.add_middleware(GZipMiddleware, minimum_size=1000)  # district / ward GeoJSON shrink ~5x on the wire
api.add_middleware(CORSMiddleware, allow_origins=config.ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
                   allow_credentials=False, max_age=86400)
api.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)   # prod with no ALLOWED_HOSTS answers nothing


@api.middleware("http")
async def cache_headers(request, call_next):
    """Built files under /assets/ have a content hash in their name, so they never change: cache them for a year.
    Everything else (index.html, manifest) is revalidated (cheap 304 via ETag) so a deploy shows up on the next visit."""
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif path.endswith(".geojson"):
        resp.headers.setdefault("Cache-Control", "public, max-age=86400")  # outlines change only when the pipeline re-runs
    elif not path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-cache")
    else:
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# ------------------------------------------------------------------ errors: {"error": code, "message": short}, never echo input
@api.exception_handler(ApiError)
async def _api_error(_req: Request, e: ApiError):
    return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status)


@api.exception_handler(api_v1.Problem)
async def _problem(_req: Request, e: api_v1.Problem):
    return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status, headers=e.headers)


@api.exception_handler(api_v1.secure.NotConfigured)
async def _not_configured(_req: Request, _e: Exception):
    return JSONResponse({"error": "not_configured", "message": "This feature isn't set up on this server"}, status_code=503)


@api.exception_handler(RequestValidationError)
async def _invalid(_req: Request, e: RequestValidationError):
    fields = sorted({".".join(str(x) for x in err["loc"][1:]) or "body" for err in e.errors()})
    return JSONResponse({"error": "invalid_input", "message": "Check these fields: " + ", ".join(fields)[:200]}, status_code=422)


@api.exception_handler(StarletteHTTPException)
async def _http(_req: Request, e: StarletteHTTPException):
    if e.status_code == 400 and "parsing the body" in str(e.detail):     # e.g. JSON nested too deep to parse: same as broken JSON
        return JSONResponse({"error": "invalid_input", "message": "Check these fields: body"}, status_code=422)
    code ={404: "not_found", 405: "method_not_allowed"}.get(e.status_code, "http_error")
    return JSONResponse({"error": code, "message": code.replace("_", " ").capitalize()}, status_code=e.status_code)


@api.exception_handler(weather.WeatherUnavailable)
async def _no_weather(_req: Request, _e: Exception):
    return JSONResponse({"error": "weather_unavailable", "message": "Forecast not available right now"}, status_code=503)


@api.exception_handler(Exception)
async def _crash(_req: Request, _e: Exception):
    return JSONResponse({"error": "internal", "message": "Something went wrong"}, status_code=500)


# ------------------------------------------------------------------ input models (spec §6.1: extra fields, NaN and unknown values -> 422)
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Devices(Strict):
    fan: bool = False
    cooler: bool = False
    ac: bool = False


class IndividualIn(Strict):
    lat: float = Field(..., **LAT)
    lon: float = Field(..., **LON)
    roof: Roof
    vulnerable: List[Vulnerable] = Field(default=[], max_length=5)
    devices: Devices = Devices()
    roof_access: bool = True
    cross_ventilation: Optional[bool] = None
    budget: Optional[Union[Literal["free", "low", "medium", "high"], int]] = Field(default=None)
    lang: Lang = "en"
    people: List[Person] = Field(default=[], max_length=20)
    tenure: Optional[Literal["own", "rent", "other"]] = None
    power_cuts: Optional[bool] = None
    power_cut_hours: List[Tuple[Clock, Clock]] = Field(default=[], max_length=6)
    water_short: Optional[bool] = None


class Reading(Strict):
    indoor_c: Optional[float] = Field(default=None, ge=10, le=55)
    outdoor_c: Optional[float] = Field(default=None, ge=-10, le=60)


class EffectIn(Strict):
    before: List[Reading] = Field(default=[], max_length=400)
    after: List[Reading] = Field(default=[], max_length=400)


def in_india(lat: float, lon: float) -> dict:
    """The district polygon at a point, or 422 (spec §6.1)."""
    d = districts.district_at(lat, lon)
    if not d:
        raise ApiError(422, "outside_india", "This place is outside India")
    return d


def india_point(lat: float = Query(..., **LAT), lon: float = Query(..., **LON)) -> tuple:
    return lat, lon, in_india(lat, lon)


# ------------------------------------------------------------------ helpers
def _now():
    return datetime.now(IST).strftime("%Y-%m-%dT%H:00")


def _now_dt():
    return datetime.now(IST).replace(tzinfo=None)


def _afternoon(w):
    """This afternoon's (or, after 5 pm, tomorrow's) mean humidity and wet-bulb, for the cooler / khus advice."""
    times = [r["time"] for r in w["hourly"]]
    return {"afternoon_rh_pct": solutions.afternoon_mean(times, [r["rh"] for r in w["hourly"]], _now_dt()),
            "afternoon_twb_c": solutions.afternoon_mean(times, [r["twb"] for r in w["hourly"]], _now_dt())}


def household_of(q: IndividualIn, persons: list) -> dict:
    """The questionnaire answers in the fix catalogue's terms."""
    devices = [d for d in ("fan", "cooler", "ac") if getattr(q.devices, d)]
    budget = q.budget if not isinstance(q.budget, int) or q.budget >= 0 else None
    reasons = {r for p in persons for r in people.care_reasons(p)}
    return {"roof_type": ROOF_TYPE.get(q.roof), "top_floor": q.roof != "lower_floor", "roof_access": q.roof_access,
            "vulnerable": bool(reasons & today.CARE), "outdoor_worker": "outdoor_work" in reasons, "devices": devices,
            "cross_ventilation": q.cross_ventilation, "budget": budget}


def _headline(td, tom):
    """(label, rows) of the headline day: today before 18:00 IST, tomorrow after (spec §7.1)."""
    if _now_dt().hour < HEADLINE_SWITCH_H and td:
        return "today", td
    return ("tomorrow", tom) if tom else ("today", td)


def _heat_days(w, td, tom, district_id, lat, lon):
    """The headline day's maximum and its 1991-2020 normal, for IMD's heatwave rules."""
    label, rows = _headline(td, tom)
    if not rows:
        return []
    ds = rows[0]["time"][:10]
    tmax = w.get("daily_tmax", {}).get(ds, max(r["t"] for r in rows))
    normal = normals.point_normal_tmax(district_id, date.fromisoformat(ds), lat, lon, w.get("elevation"))[0] if district_id else None
    return [{"day": label, "date": ds, "tmax": round(tmax, 1), "normal": normal}]


def _imd(district_id, day):
    """IMD's district warning colour for that day (stored by the imd_warnings job; none until IMD onboarding)."""
    if not district_id or not day:
        return None
    with db.session() as s:
        return notify.imd_color(s, district_id, date.fromisoformat(day))


def _heat(w, lat, lon, district_id, in_delhi):
    """(risk, next24, today, tomorrow): the heat level from the weather, IMD's rules and IMD's district warning only."""
    nxt, td, tom = weather.split_days(w, _now())
    if not nxt:
        return None, nxt, td, tom
    days = _heat_days(w, td, tom, district_id, lat, lon)
    station = normals.station_type(lat, lon, w.get("elevation"))
    r = rules.risk(nxt, td, tom, in_delhi=in_delhi, days=days, station=station, imd_color=_imd(district_id, days[0]["date"] if days else None))
    r["headline_day"] = days[0]["day"] if days else None
    return r, nxt, td, tom


def _in_delhi_bbox(lat, lon):
    return DELHI_BBOX[0] <= lat <= DELHI_BBOX[2] and DELHI_BBOX[1] <= lon <= DELHI_BBOX[3]


def _day_summary(rows):
    if not rows:
        return None
    return {"tmax": max(r["t"] for r in rows), "tmin": min(r["t"] for r in rows), "hi_max": max(r["hi"] for r in rows),
            "twb_max": max(r["twb"] for r in rows), "hi_level": rules.LEVELS[rules.base_from_heat_index(max(r["hi"] for r in rows))],
            "peak_hours": [r["time"][11:16] for r in rows if r["hi"] >= max(x["hi"] for x in rows) - 1.0]}


def _ward_summary(w):
    return {"ward": w["ward_name"].title(), "ward_no": w["ward_no"], "district": w["district"], "lst_day_c": w["lst_day_mean_c"],
            "lst_night_c": w["lst_night_mean_c"], "hvi": w["hvi"], "hvi_class": w["hvi_class"], "drivers": w.get("drivers") or [],
            "lst_day_pct": areas.percentile("lst_day_mean_c", w["lst_day_mean_c"])}


def where_info(lat: float, lon: float) -> dict:
    """Everything we know about a point: name (GeoNames), official district (LGD polygons) + its heat data, Delhi ward."""
    out = {"lat": round(lat, 5), "lon": round(lon, 5), **places.describe(lat, lon)}
    d = districts.district_at(lat, lon)
    if d:
        out["in_india"] = True
        out["district"] = d["district"]          # official LGD name beats GeoNames' older admin names
        out["state"] = d.get("state") or out.get("state")
        out["district_heat"] = {**districts.public(d), "pct": districts.percentiles(d)}
    else:
        out["in_india"] = False
        out["district_heat"] = None
    w = areas.ward_at(lat, lon) if _in_delhi_bbox(lat, lon) else None
    out["in_delhi"] = bool(w)
    out["ward"] = _ward_summary(w) if w else None
    if not out.get("label"):
        out["label"] = out.get("district") or out.get("state") or ""
    return out


@lru_cache(maxsize=1)
def _emergency_rows() -> dict:
    with open(os.path.join(DATA, "emergency_numbers.csv"), newline="", encoding="utf-8") as f:
        return {r["state"]: r for r in csv.DictReader(f)}


def emergency(state: Optional[str]) -> dict:
    """112 everywhere; a state ambulance number only when its row is Verified (spec §6.2)."""
    r = _emergency_rows().get(state or "")
    amb = r if r and r["status"].strip().lower().startswith("verified") else None
    return {"emergency": "112", "ambulance": amb["number"] if amb else None, "ambulance_service": amb["service"] if amb else None,
            "ambulance_source": amb["source_url"] if amb else None}


@lru_cache(maxsize=None)
def _json(name: str):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------ routes
@api.get("/api/health")
def health():
    return {"ok": True, "time": _now(), "db_ok": db.ok(), "model_loaded": indoor._model.cache_info().currsize > 0,
            "gazetteer_loaded": places._places.cache_info().currsize > 0, **weather.status(),
            "imd_last_ok_at": (lambda t: t.isoformat(timespec="seconds") if t else None)(imd.latest_fetch())}


@api.get("/api/version")
def version():
    return {"api": API_VERSION, "rules_sha256": _sha256(V.DEFAULT), "catalogue_version": _json("fixes.json").get("version"),
            "catalogue_updated": _json("fixes.json").get("updated"),
            "model_sha256": _sha256(indoor.MODEL), "model_card_date": None}


@api.get("/api/weather")
def get_weather(p: tuple = Depends(india_point)):
    lat, lon, d = p
    w = weather.fetch(lat, lon)
    in_delhi = bool(_in_delhi_bbox(lat, lon) and areas.ward_at(lat, lon))
    risk, nxt, td, tom = _heat(w, lat, lon, d["id"], in_delhi)
    return {"now": nxt[0] if nxt else None, "today": _day_summary(td), "tomorrow": _day_summary(tom),
            "level": risk["level"] if risk else None, "headline_day": risk["headline_day"] if risk else None,
            "next24": [{"time": r["time"], "t": r["t"], "hi": r["hi"], "twb": r["twb"], "rh": r["rh"]} for r in nxt],
            "fetched_at": w["fetched_at"], "source": w["source"], "provider": w["provider"], "stale": w["stale"],
            "approximate": w["approximate"]}


@api.get("/api/where")
def where(lat: float = Query(..., **LAT), lon: float = Query(..., **LON)):
    """Name a point anywhere in India. Offline lookup - the location is never sent to a third-party geocoder.
    A point outside the district polygons answers in_india=false (the app tells the user), not 422."""
    return where_info(lat, lon)


@api.get("/api/search")
def search(q: str = Query(..., min_length=2, max_length=60), limit: int = Query(8, ge=1, le=20)):
    """Find a place by 6-digit PIN code (or its first digits) or by name - towns, localities, villages; Hindi names work for towns."""
    return {"results": places.search(q, limit)}


def _room(q: IndividualIn, place: dict, w: dict, nxt: list, model_roof: str, home=None):
    """(hours, fit, basis, show_numbers). Model inside its training range, else the measured roof offset (spec §7.4).
    With ROOM_MODEL_MODE=validated_only the numbers are shown only in Delhi NCT; the plan still uses them.
    During power-cut hours the room is estimated with the fan and cooler off (spec §7.2)."""
    fit = indoor.applicability(nxt, place["in_delhi"])
    start = next((i for i, r in enumerate(w["hourly"]) if r["time"][:13] >= nxt[0]["time"][:13]), None)
    if fit["ok"] and start is not None:
        hours, basis = indoor.predict(w["hourly"], start, model_roof, q.devices.fan, q.devices.cooler), "model"
        if q.power_cut_hours and (q.devices.fan or q.devices.cooler):
            off = {h["time"]: h for h in indoor.predict(w["hourly"], start, model_roof, False, False)}
            hours = [off[h["time"]] if any(today.in_window(h["time"][11:16], c) for c in q.power_cut_hours) else h for h in hours]
        fit["physics_violations"] = len(indoor.physics_check(w["hourly"], hours, model_roof, q.devices.cooler))
        if fit["physics_violations"]:       # a physically impossible hour: use the measured roof offsets instead
            hours, basis = indoor.offset_estimate(nxt, model_roof), "offset"
    else:
        hours, basis = indoor.offset_estimate(nxt, model_roof), "offset"
    calibrated = basis == "model" and home is not None and calibrate.summary(home)["applied"]
    if calibrated:
        hours = calibrate.apply(hours, home)
    # numbers only where validated: Delhi NCT, or a home whose own readings calibrate it (n >= 5, spec §7.4)
    show = place["in_delhi"] or config.ROOM_MODEL_MODE == "rough_guide" or (calibrated and home.calib_n_day + home.calib_n_night >= 5)
    return hours, fit, basis, show


@api.post("/api/status/individual")
def status_individual(q: IndividualIn):
    return _status(q)


def _status(q: IndividualIn, home=None):
    d = in_india(q.lat, q.lon)
    persons = [p.model_dump(exclude_none=True) for p in q.people] or people.from_vulnerable(q.vulnerable)
    care = [p for p in persons if today.CARE & set(people.care_reasons(p))]   # work risk goes to the work advice
    place = where_info(q.lat, q.lon)
    w = weather.fetch(q.lat, q.lon)
    now = _now()
    risk, nxt, day_today, tom = _heat(w, q.lat, q.lon, d["id"], place["in_delhi"])
    if not nxt:
        raise ApiError(503, "weather_unavailable", "Forecast not available right now")
    model_roof = MODEL_ROOF.get(q.roof, q.roof)
    hours, fit, basis, show = _room(q, place, w, nxt, model_roof, home)
    risk["home"] = rules.home_factors(model_roof, care, q.devices.model_dump())   # listed beside the level, not added to it
    fixes = solutions.recommend("family", {"climate": solutions.climate_of(place.get("district_heat"))}, household_of(q, persons),
                                {"heat_level": risk["level"], **_afternoon(w)}, q.lang)
    # fan limits: the strictest person's group, on the cautious (high) end of the room range (spec §2 rule 4, §7.2)
    groups = [people.fan_group(p) for p in persons]
    group = rules.strictest([g for g, _ in groups])
    precautionary = bool(groups) and all(pc for g, pc in groups if g == group)
    fan = rules.fan_advice([{"time": h["time"], "indoor": h["high"]} for h in hours] or [{"time": r["time"], "indoor": r["t"]} for r in nxt],
                           [], group=group, precautionary=precautionary)
    fan["basis"] = "indoor" if hours else "outdoor"
    day_plan = plan.build(hours, nxt, fan["limits_c"])
    day_plan["estimate"] = basis
    advice = today.build(persons, hours, nxt, day_plan, risk["level_index"], q.devices.model_dump(), q.power_cut_hours, q.lang)
    night = [h for h in hours if h["time"][11:13] in ("02", "03", "04", "05")]
    peak = max(hours, key=lambda h: h["high"]) if hours else None
    if not show:                                       # numbers stay hidden outside Delhi; windows and fan states still work
        for h in day_plan["hours"]:
            h["indoor"] = h["low"] = h["high"] = None
    note = ("not_validated_here" if not show else "offset_estimate" if basis == "offset" else "validated_delhi")
    return {
        "time": now, "place": place, "in_delhi": place["in_delhi"], "in_india": True,
        "weather": {"now": nxt[0], "today": _day_summary(day_today), "tomorrow": _day_summary(tom), "fetched_at": w["fetched_at"],
                    "stale": w["stale"], "approximate": w["approximate"], "provider": w["provider"]},
        "indoor": {"next24": hours if show else [], "peak": peak if show else None,
                   "night_min": (min(night, key=lambda h: h["indoor"]) if night else None) if show else None,
                   "basis": basis, "numbers_shown": show, "applicability": fit, "note_code": note, "model": indoor.model_info(),
                   "roof_proxy": MODEL_ROOF.get(q.roof), "outdoor24": [{"time": r["time"], "t": r["t"]} for r in nxt]},
        "risk": risk, "fan": fan, "plan": day_plan,
        "per_person": advice["per_person"], "today_actions": advice["today_actions"], "work": today.work_plan(persons, nxt),
        "fixes": fixes,
        "how": {"risk": "weather only: IMD heat-index bands (on the air temperature when higher) + IMD heatwave rules (45 / 47 C, or "
                        "4.5 / 6.4 C above the 1991-2020 normal; plains, hill and coastal limits) for the headline day + wet-bulb danger limit"
                        + (" + Delhi HAP two-day rule" if place["in_delhi"] else "") + "; home factors listed separately",
                "indoor": ("XGBoost on measured Delhi homes, shown as an 80 % range" if basis == "model"
                           else "outdoor air plus the measured roof offset (forecast outside the model's training range)")
                          + ("" if show else "; numbers not shown outside Delhi"),
                "fan": "published fan limits applied to the high end of the " + ("room range" if hours else "outdoor air"),
                "windows": "open when outdoor air is below the low end of the room's range, close when above the high end",
                "fixes": "one catalogue (fixes.json): triggered by your answers and today's heat level, filtered by roof, roof access, budget, afternoon wet-bulb and climate; measured fixes first"},
        "health": {"signs": V.value("health.signs.ncdc_public_2026"), "advice": V.value("health.advice.ncdc_iec"),
                   "emergency": emergency(place.get("state")),
                   "cool_first": V.value("health.cool_first_transport_second")["rule"],
                   "sources": [V.source("health.signs.ncdc_public_2026"), V.source("health.advice.ncdc_iec"), V.source("health.cool_first_transport_second")]},
        "disclaimer": "Guidance, not a diagnosis. In an emergency call 112.",
    }


class MeStatusIn(Strict):
    day: Literal["today", "tomorrow"] = "today"
    people: List[Person] = Field(default=[], max_length=20)


class OutlookIn(Strict):
    days: int = Field(default=5, ge=1, le=7)
    people: List[Person] = Field(default=[], max_length=20)


@api.post("/api/v1/households/me/status", dependencies=[Depends(households.enabled)])
def me_status(q: MeStatusIn, hid: str = Depends(api_v1.household)):
    """The saved home's status; the people come from the phone (spec §6.3). Calibration and fix progress: Phase 6."""
    with db.session() as s:
        h = s.get(households.Household, hid)
        answers = households.stored_answers(h)
        calib = calibrate.summary(h)
        fixes_done = learn.progress(s, hid)
    out = _status(IndividualIn(**answers, people=q.people), home=h)
    dh = out["place"].get("district_heat") or {}
    out.update({"day": q.day, "calibration": calib, "fix_progress": fixes_done,
                "imd_warning": _imd(dh.get("id"), (datetime.now(IST).date()).isoformat())})
    if q.day == "tomorrow":
        out["tomorrow_outlook"] = _outlook(answers, [p.model_dump(exclude_none=True) for p in q.people], 2)[1:]
    return out


def _outlook(answers: dict, persons: list, days: int) -> list:
    lat, lon = answers["lat"], answers["lon"]
    d = in_india(lat, lon)
    in_delhi = bool(_in_delhi_bbox(lat, lon) and areas.ward_at(lat, lon))
    w = weather.fetch(lat, lon)
    first = datetime.now(IST).date().isoformat()
    dates = sorted({r["time"][:10] for r in w["hourly"] if r["time"][:10] >= first})[:days]
    persons = persons or people.from_vulnerable([])
    out = []
    for i, ds in enumerate(dates):
        imd = _imd(d["id"], ds)
        lv = levels.day_level(w, ds, lat, lon, d["id"], in_delhi, "today" if i == 0 else "tomorrow", imd_color=imd)
        rows = levels.day_rows(w, ds)
        tmax = w.get("daily_tmax", {}).get(ds, max(r["t"] for r in rows))
        at_risk = [k for k, p in enumerate(persons) if (lv["level_index"] >= 1 and today.CARE & set(people.care_reasons(p)))
                   or (p.get("outdoor_work") and levels.window_level(w, ds, p.get("work_start") or today.WORK_DEFAULT[0],
                                                                       p.get("work_end") or today.WORK_DEFAULT[1]) >= 2)]
        row = {"date": ds, "level": lv["level"], "reasons": lv["reasons"], "hi_max": max(r["hi"] for r in rows), "tmax": round(tmax, 1),
               "tmin": min(r["t"] for r in rows), "twb_max": max(r["twb"] for r in rows), "persons_at_risk": at_risk}
        if imd:
            row["imd_color"] = imd
        if in_delhi or config.ROOM_MODEL_MODE == "rough_guide":   # room numbers only where they were validated (spec §7.4)
            o = V.value(indoor.OFFSET_KEY[MODEL_ROOF.get(answers["roof"], answers["roof"])])["afternoon_iqr"]
            row["room_peak_range"] = [round(tmax + o[0], 1), round(tmax + o[1], 1)]
        out.append(row)
    return out


@api.post("/api/v1/households/me/outlook", dependencies=[Depends(households.enabled)])
def me_outlook(q: OutlookIn, hid: str = Depends(api_v1.household)):
    with db.session() as s:
        answers = households.stored_answers(s.get(households.Household, hid))
    return {"days": _outlook(answers, [p.model_dump(exclude_none=True) for p in q.people], q.days)}


@api.get("/api/area")
def area(p: tuple = Depends(india_point), lang: Lang = "en"):
    """Colony / society view: the district's heat profile (all India) + the Delhi ward when inside Delhi."""
    lat, lon, _ = p
    info = where_info(lat, lon)
    ward_full = areas.ward_at(lat, lon) if info["in_delhi"] else None
    try:
        w = weather.fetch(lat, lon)
        risk, _, _, _ = _heat(w, lat, lon, info["district_heat"].get("id"), info["in_delhi"])
        wx = {"heat_level": risk["level"] if risk else None, **_afternoon(w)}
    except weather.WeatherUnavailable:  # no forecast: the colony list still shows everything that doesn't depend on today
        wx = None
    sol = solutions.recommend("colony", {"climate": solutions.climate_of(info["district_heat"])}, None, wx, lang)
    cost_ok = V.shown_ok("cost.coolroof_per_m2")           # spec §2 rule 3: a price is shown only when Verified
    return {"where": info, "district": info["district_heat"], "ward": ward_full,
            "ward_percentiles": {k: areas.percentile(k, ward_full[k]) for k in ["lst_day_mean_c", "lst_night_mean_c", "hvi", "frac_tree"]} if ward_full else None,
            "solutions": sol,
            "coolroof_cost_inr_per_m2": V.value("cost.coolroof_per_m2")["inr_per_m2"] if cost_ok else None,
            "coolroof_effect_c": V.value("coolroof.indoor_drop"),
            "sources": ([V.source("cost.coolroof_per_m2")] if cost_ok else []) + [V.source("coolroof.indoor_drop")]}


@api.get("/api/gov/rank")
def gov_rank(scope: Literal["india", "delhi"] = "india", state: Optional[str] = Query(None, max_length=60),
             district: Optional[str] = Query(None, max_length=60), limit: int = Query(100, ge=1, le=800), lang: Lang = "en"):
    """scope=india: all-India district ranking (optionally one state). scope=delhi: Delhi ward ranking (extra detail)."""
    sol = solutions.recommend("government", None, None, None, lang)
    if scope == "delhi":
        d = _json("gov_rank.json")
        wards = [w for w in d["wards"] if not district or w["district"] == district]
        return {"scope": "delhi", "wards": wards[:limit], "districts": sorted({w["district"] for w in d["wards"]}),
                "checks": _json("hvi_checks.json"), "solutions": sol,
                "notes": ["Ward boundaries are pre-2022 (290 units); 2022 delimitation not openly available.",
                          "Roof shares are Census 2011 (district); JJ counts are DUSIB 2022 (district).",
                          "HVI equal-weight vs PCA-weight rank correlation 0.63 - treat ranks as indicative."]}
    r = districts.ranking(state, limit)
    chk = districts.checks()
    return {"scope": "india", **r, "checks": chk, "solutions": sol, "notes": chk.get("notes", [])}


@api.get("/api/gov/scenario")
def gov_scenario(wards: Optional[str] = Query(None, max_length=2400, pattern=r"^[A-Za-z0-9_]+(,[A-Za-z0-9_]+)*$"),
                 tree_pp: float = Query(10, ge=1, le=50), source: Literal["built", "bare"] = Query("built", alias="from")):
    """Delhi ward cooling scenario: turn tree_pp percentage points of each ward's built-up (or bare) land into tree cover and
    estimate the change in ward mean surface temperature (engine/scenario.py). No wards given means all of them."""
    rows = _json("gov_rank.json")["wards"]
    if wards:
        want = set(wards.split(","))
        if len(want) > 300:
            raise ApiError(422, "invalid_input", "At most 300 wards")
        rows = [w for w in rows if w["ward_no"] in want]
    return scenario.simulate(rows, tree_pp, source)


@api.get("/api/gov/plan_trees")
def gov_plan_trees(area_km2: Optional[float] = Query(None, gt=0, le=100), budget_inr: Optional[float] = Query(None, gt=0, le=1e12),
                   source: Literal["built", "bare"] = Query("built", alias="from"),
                   objective: Literal["people", "elderly", "vulnerable"] = "people", max_pp: float = Query(20, ge=1, le=50)):
    """Delhi: where to plant area_km2 (or budget_inr worth) of new tree cover for the most cooling where people live
    (engine/scenario.optimise). Neither given means 5 km2."""
    if area_km2 is not None and budget_inr is not None:
        raise ApiError(422, "invalid_input", "Give area_km2 or budget_inr, not both")
    if area_km2 is None and budget_inr is None:
        area_km2 = 5
    return scenario.optimise(_json("gov_rank.json")["wards"], area_km2, source, objective, max_pp, budget_inr)


@api.get("/api/gov/plan_coolroofs")
def gov_plan_coolroofs(budget_inr: float = Query(..., gt=0, le=1e12),
                       objective: Literal["people", "elderly", "vulnerable"] = "people"):
    """Delhi: which wards' sheet-roof homes a cool-roof budget should reach first (engine/scenario.plan_coolroofs)."""
    return scenario.plan_coolroofs(_json("gov_rank.json")["wards"], budget_inr, objective)


@api.get("/api/gov/hotspots")
def gov_hotspots(city: Optional[str] = Query(None, pattern=r"^[a-z]{2,20}$")):
    """City surface-heat hotspots (1 km cells, ml/model_a/build_city_hotspots.py). No city: the list of cities with summaries.
    Includes the satellite-vs-station air temperature check (ml/validation/lst_vs_air.py) so the map is read correctly."""
    if not os.path.exists(os.path.join(DATA, "city_hotspots.json")):
        raise ApiError(503, "not_built", "City hotspots not built yet")
    d = _json("city_hotspots.json")
    check = _json("lst_vs_air.json") if os.path.exists(os.path.join(DATA, "lst_vs_air.json")) else None
    if city is None:
        return {"cities": [{"key": k, "name": c["name"], "lst_median_c": c["lst_median_c"], "cells": len(c["cells"])}
                           for k, c in d["cities"].items()], "caveats": d["caveats"], "air_check": check}
    if city not in d["cities"]:
        raise ApiError(404, "not_found", "No hotspot map for this city")
    return {"key": city, **d["cities"][city], "source": d["source"], "caveats": d["caveats"], "air_check": check}


@api.get("/api/outdoor")
def outdoor_now(p: tuple = Depends(india_point)):
    """Outside air temperature for this hour at a point, from the forecast already cached for its cell
    (pairs with a family's indoor thermometer reading)."""
    lat, lon, _ = p
    w = weather.fetch(lat, lon)
    nxt, _, _ = weather.split_days(w, _now())
    if not nxt:
        raise ApiError(503, "weather_unavailable", "Forecast not available right now")
    return {"time": nxt[0]["time"], "outdoor_c": nxt[0]["t"]}


@api.post("/api/fix_effect")
def fix_effect(q: EffectIn):
    """How much a fix helped in this home, from its own before/after readings (stored on the device; nothing is kept here)."""
    return solutions.estimate_fix_effect([r.model_dump() for r in q.before], [r.model_dump() for r in q.after])


@api.get("/api/wards/list")
def wards_list():
    d = _json("gov_rank.json")
    return sorted(({"no": w["ward_no"], "name": w["ward_name"].title(), "district": w["district"], "lat": w["lat"], "lon": w["lon"]}
                   for w in d["wards"] if w.get("lat")), key=lambda x: x["name"])


@api.get("/api/wards.geojson")
def wards_geojson():
    return FileResponse(os.path.join(DATA, "wards.geojson"), media_type="application/geo+json")


@api.get("/api/india/districts.geojson")
def districts_geojson():
    if not districts.available():
        raise ApiError(503, "not_built", "District layer not built yet")
    return FileResponse(districts.PATH, media_type="application/geo+json")


@api.get("/api/about")
def about():
    """Model facts for the How-it-works page, read from the model cards (no numbers typed into the frontend)."""
    ind = _json("indoor_model_card.json")
    ma = _json("model_a_card.json")
    best = next(c for c in ma["comparison"] if c["model"] == ma["best"])
    chk = districts.checks()
    return {"indoor": {"mae_c": ind["cv_mae_all"], "rule_mae_c": ind.get("baseline_rule_mae"), "homes": ind["n_homes"], "rows": ind["n_rows"],
                       "band_c": [ind["residual_p10"], ind["residual_p90"]], "validation": ind["validation"], "applicability": ind.get("applicability")},
            "districts": {"n": chk.get("n_with_index"), "spearman_equal_vs_pca": chk.get("spearman_equal_vs_pca"), "years": chk.get("years")},
            "wards": {"model": ma["best"], "r2": best["R2"], "mae_c": best["spatial_cv_MAE"], "validation": ma["validation"], "n_wards": areas.city_stats()["n_wards"]}}


@api.get("/api/sources")
def sources():
    return {"sources": _json("sources.json"),
            "verified_numbers": [{"key": k, "status": r["status"], "source": r["source_title"], "url": r["doi_or_url"]} for k, r in V.table().items()]}


api.include_router(api_v1.router)
api.include_router(households.router)
api.include_router(workers.router)
api.include_router(learn.router)
api.include_router(gov.router)
api.include_router(api_v1.internal)

if WEB:
    api.mount("/", StaticFiles(directory=WEB, html=True), name="web")

def _index_html():
    if not WEB:
        return None
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        return f.read()


app = http.Guard(api, http.site_csp(_index_html()))
