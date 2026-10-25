"""Live weather (BACKEND_SPEC §4). A `WeatherProvider` returns hourly rows for a weather cell; `OpenMeteoProvider` is the
only one so far (free for non-commercial use; attribution shown next to the data).

- Cell: lat/lon rounded to 0.1 deg. Its height is Open-Meteo's own terrain model at the cell centre (returned as
  `elevation`, reported here with its 100 m bucket). A per-point height inside hill cells needs a bundled terrain file:
  the free elevation API counts every point as a call, too many for a national grid. 7 forecast days, 2 past days.
- Cache: in process, at most 5,000 cells, 30 minutes fresh; one upstream fetch per cell at a time (single-flight).
- On an upstream error: data up to 6 h old is served with stale=true.
- WEATHER_DAILY_BUDGET: at 90 % no new cells are fetched; the nearest cached cell within 25 km is served (approximate=true),
  otherwise WeatherUnavailable (the caller falls back to basic mode).
Sync httpx inside FastAPI's threadpool (the routes are sync and CPU-bound), with a 5 s timeout and 2 retries."""
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .heat import heat_index_c, wet_bulb_c

IST = ZoneInfo("Asia/Kolkata")
TTL = 1800
STALE_MAX = 6 * 3600
MAX_CELLS = 5000
NEAR_KM = 25
PAST_DAYS, FORECAST_DAYS = 2, 7


class WeatherUnavailable(Exception):
    """No forecast can be served (upstream down with nothing cached, or the budget is used up)."""


class WeatherProvider:
    name = "base"

    def get(self, lat: float, lon: float) -> dict:
        """{"hourly": [{"time": "YYYY-MM-DDTHH:00" (IST), "t", "rh", "sw", "ws"}], "daily_tmax": {date: C}, "elevation": m}"""
        raise NotImplementedError


class OpenMeteoProvider(WeatherProvider):
    name = "open-meteo"

    def __init__(self, api_key: str = "", timeout: float = 5.0, retries: int = 2):
        self.base = "https://customer-api.open-meteo.com/v1/forecast" if api_key else "https://api.open-meteo.com/v1/forecast"
        self.api_key, self.timeout, self.retries = api_key, timeout, retries

    def get(self, lat, lon):
        params = {"latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "past_days": PAST_DAYS, "forecast_days": FORECAST_DAYS,
                  "hourly": "temperature_2m,relative_humidity_2m,shortwave_radiation,wind_speed_10m", "daily": "temperature_2m_max"}
        if self.api_key:
            params["apikey"] = self.api_key
        last = None
        for attempt in range(self.retries + 1):
            try:
                r = httpx.get(self.base, params=params, timeout=self.timeout)
                r.raise_for_status()
                return parse_open_meteo(r.json())
            except (httpx.HTTPError, ValueError, KeyError) as e:
                last = e
                if attempt < self.retries:
                    time.sleep(0.5 * 2 ** attempt)
        raise WeatherUnavailable(f"open-meteo: {type(last).__name__}")


def parse_open_meteo(d: dict) -> dict:
    """Validate the payload before it is cached (spec §8.9): equal-length arrays, IST hours, physical ranges."""
    h = d["hourly"]
    cols = ("time", "temperature_2m", "relative_humidity_2m", "shortwave_radiation", "wind_speed_10m")
    n = len(h["time"])
    if n == 0 or any(len(h[c]) != n for c in cols) or d.get("timezone") != "Asia/Kolkata":
        raise ValueError("bad forecast payload")
    rows = []
    for i in range(n):
        t, rh = h["temperature_2m"][i], h["relative_humidity_2m"][i]
        if t is None or rh is None:
            continue
        if not (-40 <= t <= 60 and 0 <= rh <= 100):
            raise ValueError("forecast value out of physical range")
        rows.append({"time": h["time"][i], "t": t, "rh": rh, "sw": h["shortwave_radiation"][i] or 0.0, "ws": h["wind_speed_10m"][i] or 0.0})
    daily = d.get("daily") or {}
    tmax = {t: x for t, x in zip(daily.get("time", []), daily.get("temperature_2m_max", []), strict=False) if x is not None and -40 <= x <= 60}
    return {"hourly": rows, "daily_tmax": tmax, "elevation": d.get("elevation")}


# ------------------------------------------------------------------ cells
def cell_of(lat: float, lon: float) -> tuple:
    return (round(lat, 1), round(lon, 1))


def _km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


# ------------------------------------------------------------------ cache, single-flight, budget
_CACHE: "OrderedDict[tuple, tuple[float, dict]]" = OrderedDict()
_LOCK = threading.Lock()
_CELL_LOCKS: dict = {}
_STATE = {"provider": None, "last_ok_at": None, "day": None, "calls": 0}


def provider() -> WeatherProvider:
    if _STATE["provider"] is None:
        from app import config
        if config.WEATHER_PROVIDER != "open-meteo":
            raise RuntimeError(f"unknown WEATHER_PROVIDER {config.WEATHER_PROVIDER!r}")
        _STATE["provider"] = OpenMeteoProvider(config.OPEN_METEO_API_KEY)
    return _STATE["provider"]


def set_provider(p: WeatherProvider):
    """For tests: swap the provider and clear the cache."""
    with _LOCK:
        _STATE["provider"] = p
        _CACHE.clear()
        _STATE.update(day=None, calls=0)


def _budget_left() -> bool:
    from app import config
    today = datetime.now(IST).date().isoformat()
    if _STATE["day"] != today:
        _STATE["day"], _STATE["calls"] = today, 0
    return config.WEATHER_DAILY_BUDGET is None or _STATE["calls"] < 0.9 * config.WEATHER_DAILY_BUDGET


def _out(key, entry, stale=False, approximate=False):
    ts, data = entry
    rows = [{**r, "hi": round(heat_index_c(r["t"], r["rh"]), 1), "twb": round(wet_bulb_c(r["t"], r["rh"]), 1)} for r in data["hourly"]]
    elev = data.get("elevation")
    return {"lat": key[0], "lon": key[1], "elevation": elev, "elev_bucket_m": None if elev is None else int(round(elev / 100.0)) * 100,
            "fetched_at": datetime.fromtimestamp(ts, IST).isoformat(timespec="minutes"), "hourly": rows,
            "daily_tmax": data["daily_tmax"], "source": "Open-Meteo forecast API (open-meteo.com)",
            "provider": provider().name, "stale": stale, "approximate": approximate}


def _nearest_cached(key):
    best = None
    for k, (ts, d) in _CACHE.items():
        dist = _km(key, k)
        if dist <= NEAR_KM and time.time() - ts < STALE_MAX and (best is None or dist < best[0]):
            best = (dist, k, (ts, d))
    return best


def fetch(lat: float, lon: float) -> dict:
    key = cell_of(lat, lon)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return _out(key, hit)
    with _LOCK:
        cell_lock = _CELL_LOCKS.setdefault(key, threading.Lock())
    with cell_lock:                                       # single-flight: one upstream call per cell at a time
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL:
            return _out(key, hit)
        with _LOCK:
            allowed = _budget_left() or hit is not None   # a cell already cached may refresh; new cells wait for budget
        if not allowed:
            near = _nearest_cached(key)
            if near:
                return _out(near[1], near[2], stale=time.time() - near[2][0] >= TTL, approximate=True)
            raise WeatherUnavailable("daily weather budget used")
        try:
            with _LOCK:
                _STATE["calls"] += 1
            data = provider().get(key[0], key[1])
        except WeatherUnavailable:
            if hit and time.time() - hit[0] < STALE_MAX:
                return _out(key, hit, stale=True)
            raise
        entry = (time.time(), data)
        with _LOCK:
            _CACHE[key] = entry
            _CACHE.move_to_end(key)
            while len(_CACHE) > MAX_CELLS:
                _CACHE.popitem(last=False)
            _STATE["last_ok_at"] = datetime.now(IST).isoformat(timespec="seconds")
    return _out(key, entry)


def status() -> dict:
    from app import config
    return {"weather_provider": provider().name, "weather_last_ok_at": _STATE["last_ok_at"], "weather_calls_today": _STATE["calls"],
            "weather_daily_budget": config.WEATHER_DAILY_BUDGET, "weather_cells_cached": len(_CACHE)}


def split_days(w: dict, now_iso: str):
    """Return (next24 rows, today rows, tomorrow rows) relative to now (local time)."""
    now = now_iso[:13]
    future = [r for r in w["hourly"] if r["time"][:13] >= now]
    today = [r for r in w["hourly"] if r["time"][:10] == now_iso[:10]]
    tomorrow_date = sorted({r["time"][:10] for r in future if r["time"][:10] > now_iso[:10]})
    tomorrow = [r for r in w["hourly"] if tomorrow_date and r["time"][:10] == tomorrow_date[0]]
    return future[:24], today, tomorrow
