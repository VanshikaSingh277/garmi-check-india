"""Thandak - heat-risk API + static frontend (one service). Works for any point in India;
Delhi additionally gets ward-level detail.
Run locally:  uvicorn main:app --reload --port 8000   (from apps/api)
"""
import json
import os
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import areas, districts, indoor, places, plan, rules, solutions, weather
from engine import verified as V

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
# the built frontend (npm run build in apps/web); the Docker image copies it to ../web
WEB = next((p for p in (os.path.join(HERE, "..", "web", "dist"), os.path.join(HERE, "..", "web")) if os.path.isfile(os.path.join(p, "index.html"))), None)
# the Android / iOS app (Capacitor) calls the API from its own origin; extra web origins can be added with THANDAK_ORIGINS
APP_ORIGINS = ["capacitor://localhost", "https://localhost", "http://localhost"] + [o for o in os.environ.get("THANDAK_ORIGINS", "").split(",") if o]
IST = ZoneInfo("Asia/Kolkata")
DELHI_BBOX = (28.40, 76.83, 28.89, 77.35)
ROOFS = {"tin_top", "stone_slab_top", "rcc_brick_top", "lower_floor"}
VULN = {"elderly", "child", "pregnant", "chronic", "outdoor_worker"}
LAT = dict(ge=6, le=37.2)
LON = dict(ge=68, le=97.6)

app = FastAPI(title="Thandak API", version="0.2.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)  # district / ward GeoJSON shrink ~5x on the wire
app.add_middleware(CORSMiddleware, allow_origins=APP_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"], max_age=86400)


@app.middleware("http")
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
    return resp


@app.on_event("startup")
def _warm():
    places.warm()  # ~2 s: load the offline gazetteer once, not on the first user's request


class Devices(BaseModel):
    fan: bool = False
    cooler: bool = False
    ac: bool = False


class IndividualIn(BaseModel):
    lat: float = Field(..., **LAT)
    lon: float = Field(..., **LON)
    roof: str
    vulnerable: List[str] = []
    devices: Devices = Devices()
    roof_access: bool = True
    lang: str = "en"


def _now():
    return datetime.now(IST).strftime("%Y-%m-%dT%H:00")


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
        out["district_heat"] = None
    w = areas.ward_at(lat, lon) if _in_delhi_bbox(lat, lon) else None
    out["in_delhi"] = bool(w)
    out["ward"] = _ward_summary(w) if w else None
    if not out.get("label"):
        out["label"] = out.get("district") or out.get("state") or ""
    return out


@app.get("/api/health")
def health():
    return {"ok": True, "time": _now()}


@app.get("/api/weather")
def get_weather(lat: float = Query(..., **LAT), lon: float = Query(..., **LON)):
    w = weather.fetch(lat, lon)
    nxt, today, tom = weather.split_days(w, _now())
    return {"now": nxt[0] if nxt else None, "today": _day_summary(today), "tomorrow": _day_summary(tom),
            "next24": [{"time": r["time"], "t": r["t"], "hi": r["hi"], "twb": r["twb"], "rh": r["rh"]} for r in nxt],
            "fetched_at": w["fetched_at"], "source": w["source"]}


@app.get("/api/where")
def where(lat: float = Query(..., **LAT), lon: float = Query(..., **LON)):
    """Name a point anywhere in India. Offline lookup - the location is never sent to a third-party geocoder."""
    return where_info(lat, lon)


@app.get("/api/search")
def search(q: str = Query(..., min_length=2, max_length=60), limit: int = Query(8, ge=1, le=20)):
    """Find a place by 6-digit PIN code (or its first digits) or by name - towns, localities, villages; Hindi names work for towns."""
    return {"results": places.search(q, limit)}


@app.post("/api/status/individual")
def status_individual(q: IndividualIn):
    if q.roof not in ROOFS:
        raise HTTPException(400, "roof must be one of " + ", ".join(sorted(ROOFS)))
    vul = [v for v in q.vulnerable if v in VULN]
    place = where_info(q.lat, q.lon)
    w = weather.fetch(q.lat, q.lon)
    now = _now()
    nxt, today, tom = weather.split_days(w, now)
    if not nxt:
        raise HTTPException(503, "forecast unavailable")
    start = next(i for i, r in enumerate(w["hourly"]) if r["time"][:13] >= now[:13])
    fit = indoor.applicability(nxt, place["in_delhi"])
    ind = indoor.predict(w["hourly"], start, q.roof, q.devices.fan, q.devices.cooler) if fit["ok"] else []
    peak = max(ind, key=lambda h: h["indoor"]) if ind else None
    risk = rules.risk(nxt, today, tom, q.roof, vul, q.devices.model_dump(), peak["indoor"] if peak else None, in_delhi=place["in_delhi"])
    # fan limits are about the air around the person: the indoor estimate when we trust it, else the outdoor air (labelled)
    fan = rules.fan_advice(ind or [{"time": r["time"], "indoor": r["t"]} for r in nxt], vul)
    fan["basis"] = "indoor" if ind else "outdoor"
    night = [h for h in ind if h["time"][11:13] in ("02", "03", "04", "05")]
    day_plan = plan.build(ind, nxt, fan["limits_c"])
    note = "outside_training_range" if not fit["ok"] else ("validated_delhi" if place["in_delhi"] else "not_validated_here")
    return {
        "time": now, "place": place, "in_delhi": place["in_delhi"], "in_india": place.get("in_india", False),
        "weather": {"now": nxt[0], "today": _day_summary(today), "tomorrow": _day_summary(tom), "fetched_at": w["fetched_at"]},
        "indoor": {"next24": ind, "peak": peak, "night_min": min(night, key=lambda h: h["indoor"]) if night else None,
                   "applicability": fit, "note_code": note, "model": indoor.model_info(),
                   "outdoor24": [{"time": r["time"], "t": r["t"]} for r in nxt]},
        "risk": risk, "fan": fan, "plan": day_plan,
        "solutions": solutions.pick("individual", q.roof, q.roof_access, q.lang),
        "how": {"risk": "IMD heat-index bands + IMD heat-wave (Tmax >= 45 C) + wet-bulb danger limit"
                        + (" + Delhi HAP two-day rule" if place["in_delhi"] else "") + "; home factors raise it only when it is hot",
                "indoor": "XGBoost on 56 measured Delhi homes; leave-home-out MAE 1.5 C; shown as an 80 % range",
                "fan": "published fan limits applied to the " + ("room estimate" if ind else "outdoor air"),
                "windows": "open when outdoor air is below the low end of the room's predicted range" if ind else "not shown (no indoor estimate)",
                "fixes": "verified catalogue filtered by role, roof type and roof access; ordered free -> low -> medium -> high cost"},
        "health": {"signs": V.value("health.signs.delhi_hap"), "advice": V.value("health.advice.ncdc_iec"),
                   "emergency": {"ambulance": "108", "emergency": "112"},
                   "cool_first": V.value("health.cool_first_transport_second")["rule"],
                   "sources": [V.source("health.signs.delhi_hap"), V.source("health.advice.ncdc_iec"), V.source("health.cool_first_transport_second")]},
        "disclaimer": "Guidance, not a diagnosis. In an emergency call 108 (ambulance) or 112.",
    }


@app.get("/api/area")
def area(lat: float = Query(..., **LAT), lon: float = Query(..., **LON), lang: str = "en"):
    """Colony / society view: the district's heat profile (all India) + the Delhi ward when inside Delhi."""
    info = where_info(lat, lon)
    if not info.get("in_india") or not info.get("district_heat"):
        raise HTTPException(404, "No Indian district at this point")
    ward_full = areas.ward_at(lat, lon) if info["in_delhi"] else None
    return {"where": info, "district": info["district_heat"], "ward": ward_full,
            "ward_percentiles": {k: areas.percentile(k, ward_full[k]) for k in ["lst_day_mean_c", "lst_night_mean_c", "hvi", "frac_tree"]} if ward_full else None,
            "solutions": solutions.pick("society", "any", True, lang),
            "coolroof_cost_inr_per_m2": V.value("cost.coolroof_per_m2")["inr_per_m2"],
            "coolroof_effect_c": V.value("coolroof.indoor_drop"),
            "sources": [V.source("cost.coolroof_per_m2"), V.source("coolroof.indoor_drop")]}


@app.get("/api/gov/rank")
def gov_rank(scope: str = "india", state: Optional[str] = None, district: Optional[str] = None,
             limit: int = Query(100, ge=1, le=800), lang: str = "en"):
    """scope=india: all-India district ranking (optionally one state). scope=delhi: Delhi ward ranking (extra detail)."""
    sol = solutions.pick("government", "any", True, lang)
    if scope == "delhi":
        d = json.load(open(os.path.join(DATA, "gov_rank.json"), encoding="utf-8"))
        wards = [w for w in d["wards"] if not district or w["district"] == district]
        return {"scope": "delhi", "wards": wards[:limit], "districts": sorted({w["district"] for w in d["wards"]}),
                "checks": json.load(open(os.path.join(DATA, "hvi_checks.json"))), "solutions": sol,
                "notes": ["Ward boundaries are pre-2022 (290 units); 2022 delimitation not openly available.",
                          "Roof shares are Census 2011 (district); JJ counts are DUSIB 2022 (district).",
                          "HVI equal-weight vs PCA-weight rank correlation 0.63 - treat ranks as indicative."]}
    r = districts.ranking(state, limit)
    chk = districts.checks()
    return {"scope": "india", **r, "checks": chk, "solutions": sol, "notes": chk.get("notes", [])}


@app.get("/api/wards/list")
def wards_list():
    d = json.load(open(os.path.join(DATA, "gov_rank.json"), encoding="utf-8"))
    return sorted(({"no": w["ward_no"], "name": w["ward_name"].title(), "district": w["district"], "lat": w["lat"], "lon": w["lon"]}
                   for w in d["wards"] if w.get("lat")), key=lambda x: x["name"])


@app.get("/api/wards.geojson")
def wards_geojson():
    return FileResponse(os.path.join(DATA, "wards.geojson"), media_type="application/geo+json")


@app.get("/api/india/districts.geojson")
def districts_geojson():
    if not districts.available():
        raise HTTPException(503, "district layer not built yet")
    return FileResponse(districts.PATH, media_type="application/geo+json")


@app.get("/api/about")
def about():
    """Model facts for the How-it-works page, read from the model cards (no numbers typed into the frontend)."""
    ind = json.load(open(os.path.join(DATA, "indoor_model_card.json")))
    ma = json.load(open(os.path.join(DATA, "model_a_card.json")))
    best = next(c for c in ma["comparison"] if c["model"] == ma["best"])
    chk = districts.checks()
    return {"indoor": {"mae_c": ind["cv_mae_all"], "rule_mae_c": ind.get("baseline_rule_mae"), "homes": ind["n_homes"], "rows": ind["n_rows"],
                       "band_c": [ind["residual_p10"], ind["residual_p90"]], "validation": ind["validation"], "applicability": ind.get("applicability")},
            "districts": {"n": chk.get("n_with_index"), "spearman_equal_vs_pca": chk.get("spearman_equal_vs_pca"), "years": chk.get("years")},
            "wards": {"model": ma["best"], "r2": best["R2"], "mae_c": best["spatial_cv_MAE"], "validation": ma["validation"], "n_wards": areas.city_stats()["n_wards"]}}


@app.get("/api/sources")
def sources():
    return {"sources": json.load(open(os.path.join(DATA, "sources.json"), encoding="utf-8")),
            "verified_numbers": [{"key": k, "status": r["status"], "source": r["source_title"], "url": r["doi_or_url"]} for k, r in V.table().items()]}


if WEB:
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
