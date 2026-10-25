"""Re-record the Open-Meteo fixtures used by the tests (spec §10: tests never call the internet; these files are the
recorded answers). Run from the repo root when the response format may have changed:  python tests/fixtures/record.py"""
import json
import os
import time

import httpx

HERE = os.path.dirname(__file__)
PARAMS = {"timezone": "Asia/Kolkata", "hourly": "temperature_2m,relative_humidity_2m,shortwave_radiation,wind_speed_10m",
          "daily": "temperature_2m_max", "past_days": 2, "forecast_days": 7}
CELLS = {"delhi": (28.6, 77.2), "chennai": (13.1, 80.3), "jaisalmer": (26.9, 70.9), "shimla": (31.1, 77.2)}


def save(name, data):
    with open(os.path.join(HERE, f"openmeteo_{name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))


for name, (lat, lon) in CELLS.items():
    r = httpx.get("https://api.open-meteo.com/v1/forecast", params={**PARAMS, "latitude": lat, "longitude": lon}, timeout=30)
    r.raise_for_status()
    save(name, r.json())
    time.sleep(1)
# the Delhi heat-wave day of 28 May 2024, as the forecast models had it (same response format)
hist = {k: v for k, v in PARAMS.items() if k not in ("past_days", "forecast_days")}
r = httpx.get("https://historical-forecast-api.open-meteo.com/v1/forecast",
              params={**hist, "latitude": 28.6, "longitude": 77.2, "start_date": "2024-05-26", "end_date": "2024-06-03"}, timeout=30)
r.raise_for_status()
save("delhi_2024-05-28", r.json())
print("recorded", len(CELLS) + 1, "fixtures")
