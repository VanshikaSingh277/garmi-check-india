"""Sample answers the app shows when it can't reach the server, so every screen still has something to show.
They are real API answers for Delhi at 15:00 on 28 May 2024 (a recorded heatwave day: tests/fixtures/openmeteo_delhi_2024-05-28.json),
produced by the same engine with the clock frozen. The app labels them as a sample, never as today's weather.
Re-run after changing the engine, the data files or the fixture:  .venv/Scripts/python.exe -X utf8 scripts/build_sample_data.py"""
import json
import os
import sys
import time
import types
from datetime import datetime

R = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(R, "apps", "api"))
os.chdir(os.path.join(R, "apps", "api"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from engine import weather  # noqa: E402

OUT = os.path.join(R, "apps", "web", "public", "sample")
FIXTURE = os.path.join(R, "tests", "fixtures", "openmeteo_delhi_2024-05-28.json")
WHEN = datetime(2024, 5, 28, 15, 0)
LAT, LON = 28.6139, 77.2090
ROOFS = ["tin_top", "asbestos_top", "stone_slab_top", "rcc_brick_top", "lower_floor"]


class Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return WHEN.replace(tzinfo=tz) if tz else WHEN


class Recorded(weather.WeatherProvider):
    name = "recorded-sample"

    def __init__(self):
        with open(FIXTURE, encoding="utf-8") as f:
            self.data = weather.parse_open_meteo(json.load(f))

    def get(self, lat, lon):
        return self.data


main.datetime = Frozen
weather.datetime = Frozen
# The weather cache stamps "fetched_at" from time.time(); stamp it with the sample's moment too.
weather.time = types.SimpleNamespace(time=lambda: WHEN.replace(tzinfo=weather.IST).timestamp(), sleep=time.sleep)
weather.set_provider(Recorded())
client = TestClient(main.app)


def get(path):
    r = client.get(path)
    r.raise_for_status()
    return r.json()


def post(path, body):
    r = client.post(path, json=body)
    r.raise_for_status()
    return r.json()


def save(name, data):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


os.makedirs(OUT, exist_ok=True)
q = f"lat={LAT}&lon={LON}"
save("meta.json", {"date": WHEN.date().isoformat(), "time": WHEN.strftime("%H:%M"), "lat": LAT, "lon": LON})
save("where.json", get(f"/api/where?{q}"))
save("weather.json", get(f"/api/weather?{q}"))
save("outdoor.json", get(f"/api/outdoor?{q}"))
save("about.json", get("/api/about"))
for lang in ["en", "hi"]:
    save(f"area_{lang}.json", get(f"/api/area?{q}&lang={lang}"))
    save(f"rank_india_{lang}.json", get(f"/api/gov/rank?scope=india&limit=800&lang={lang}"))
    save(f"rank_delhi_{lang}.json", get(f"/api/gov/rank?scope=delhi&limit=300&lang={lang}"))
    for roof in ROOFS:
        body = {"lat": LAT, "lon": LON, "roof": roof, "vulnerable": [], "devices": {"fan": True, "cooler": False, "ac": False}, "lang": lang}
        save(f"individual_{roof}_{lang}.json", post("/api/status/individual", body))

w = json.load(open(os.path.join(OUT, "weather.json"), encoding="utf-8"))
print("sample written to", os.path.relpath(OUT, R), "| now:", w.get("now"), "| today tmax:", (w.get("today") or {}).get("tmax"))
