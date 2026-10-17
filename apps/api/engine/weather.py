"""Live weather from the Open-Meteo forecast API (free for non-commercial use; attribution shown in the footer).
Fetches the past 24 h + next 48 h hourly so the indoor model has its lag features. Cached 30 min per ~1 km cell."""
import json
import time
import urllib.request
from datetime import datetime

from .heat import heat_index_c, wet_bulb_c

API = "https://api.open-meteo.com/v1/forecast"
_CACHE: dict = {}
TTL = 1800


def fetch(lat: float, lon: float) -> dict:
    key = (round(lat, 2), round(lon, 2))
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    url = (f"{API}?latitude={key[0]}&longitude={key[1]}"
           "&hourly=temperature_2m,relative_humidity_2m,shortwave_radiation,wind_speed_10m"
           "&past_days=1&forecast_days=2&timezone=Asia%2FKolkata")
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.loads(r.read())
    h = d["hourly"]
    rows = []
    for i, ts in enumerate(h["time"]):
        t, rh = h["temperature_2m"][i], h["relative_humidity_2m"][i]
        if t is None or rh is None:
            continue
        rows.append({"time": ts, "t": t, "rh": rh, "sw": h["shortwave_radiation"][i] or 0.0, "ws": h["wind_speed_10m"][i] or 0.0,
                     "hi": round(heat_index_c(t, rh), 1), "twb": round(wet_bulb_c(t, rh), 1)})
    out = {"lat": key[0], "lon": key[1], "fetched_at": datetime.now().isoformat(timespec="minutes"), "hourly": rows,
           "source": "Open-Meteo forecast API (open-meteo.com)"}
    _CACHE[key] = (time.time(), out)
    return out


def split_days(w: dict, now_iso: str):
    """Return (next24 rows, today rows, tomorrow rows) relative to now (local time)."""
    now = now_iso[:13]
    future = [r for r in w["hourly"] if r["time"][:13] >= now]
    today = [r for r in w["hourly"] if r["time"][:10] == now_iso[:10]]
    tomorrow_date = sorted({r["time"][:10] for r in future if r["time"][:10] > now_iso[:10]})
    tomorrow = [r for r in w["hourly"] if tomorrow_date and r["time"][:10] == tomorrow_date[0]]
    return future[:24], today, tomorrow
