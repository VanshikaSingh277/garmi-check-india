"""Weather provider (BACKEND_SPEC §4, §10.2): retry, stale fallback, 7 days, provider switch, budget, single-flight,
payload checks. Uses recorded Open-Meteo responses in tests/fixtures; never calls the internet."""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
import httpx  # noqa: E402

from app import config  # noqa: E402
from engine import weather  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def raw(name):
    with open(os.path.join(FIX, f"openmeteo_{name}.json"), encoding="utf-8") as f:
        return json.load(f)


class Recorded(weather.WeatherProvider):
    """Serves a recorded response for every cell; counts calls; can be told to fail."""
    name = "recorded"

    def __init__(self, fixture="delhi", fail=False, delay=0.0):
        self.data, self.fail, self.delay, self.calls = weather.parse_open_meteo(raw(fixture)), fail, delay, 0

    def get(self, lat, lon):
        self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise weather.WeatherUnavailable("down")
        return self.data


def test_seven_forecast_days_and_two_past_days():
    rows = weather.parse_open_meteo(raw("delhi"))["hourly"]
    assert len(rows) >= (7 + 2) * 24 - 1
    d = weather.parse_open_meteo(raw("delhi_2024-05-28"))
    assert d["daily_tmax"]["2024-05-28"] >= 40          # the recorded heatwave day is hot, as it should be


def test_open_meteo_retries_then_succeeds(monkeypatch=None):
    calls = {"n": 0}
    good = raw("chennai")

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=good, request=httpx.Request("GET", url))
    orig, orig_sleep = weather.httpx.get, weather.time.sleep
    weather.httpx.get, weather.time.sleep = fake_get, lambda s: None
    try:
        out = weather.OpenMeteoProvider().get(13.1, 80.3)
        assert calls["n"] == 3 and out["hourly"]
        calls["n"] = -10                                  # always failing now
        try:
            weather.OpenMeteoProvider().get(13.1, 80.3)
        except weather.WeatherUnavailable:
            pass
        else:
            raise AssertionError("expected WeatherUnavailable")
    finally:
        weather.httpx.get, weather.time.sleep = orig, orig_sleep


def test_provider_switch_and_cell_rounding():
    p = Recorded("shimla")
    weather.set_provider(p)
    a = weather.fetch(31.104, 77.171)
    b = weather.fetch(31.096, 77.166)                     # same 0.1 deg cell: one upstream call
    assert p.calls == 1 and a["provider"] == "recorded" and (a["lat"], a["lon"]) == (31.1, 77.2)
    assert a["stale"] is False and a["approximate"] is False and b["hourly"]


def test_stale_fallback_up_to_six_hours():
    p = Recorded("delhi")
    weather.set_provider(p)
    weather.fetch(28.6, 77.2)
    key = weather.cell_of(28.6, 77.2)
    ts, data = weather._CACHE[key]
    weather._CACHE[key] = (ts - weather.TTL - 60, data)   # cached copy is now past its fresh time
    p.fail = True
    out = weather.fetch(28.6, 77.2)
    assert out["stale"] is True
    weather._CACHE[key] = (ts - weather.STALE_MAX - 60, data)
    try:
        weather.fetch(28.6, 77.2)
    except weather.WeatherUnavailable:
        pass
    else:
        raise AssertionError("data older than 6 h must not be served")


def test_budget_serves_nearest_cached_cell_then_basic_mode():
    p = Recorded("delhi")
    weather.set_provider(p)
    old = config.WEATHER_DAILY_BUDGET
    config.WEATHER_DAILY_BUDGET = 2                       # 90 % of 2 = 1.8: the second new cell is the last one fetched
    try:
        weather.fetch(28.6, 77.2)
        weather.fetch(28.7, 77.2)
        near = weather.fetch(28.8, 77.2)                  # budget used: nearest cached cell within 25 km
        assert near["approximate"] is True and p.calls == 2
        try:
            weather.fetch(13.1, 80.3)                     # nothing cached near Chennai: basic mode
        except weather.WeatherUnavailable:
            pass
        else:
            raise AssertionError("expected WeatherUnavailable")
    finally:
        config.WEATHER_DAILY_BUDGET = old


def test_single_flight_one_upstream_call_per_cell():
    p = Recorded("jaisalmer", delay=0.2)
    weather.set_provider(p)
    threads = [threading.Thread(target=weather.fetch, args=(26.9, 70.9)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert p.calls == 1


def test_bad_payloads_are_rejected_before_caching():
    d = raw("delhi")
    d["hourly"]["temperature_2m"] = d["hourly"]["temperature_2m"][:-3]
    for bad in (d, {**raw("delhi"), "timezone": "UTC"}):
        try:
            weather.parse_open_meteo(bad)
        except ValueError:
            continue
        raise AssertionError("bad payload accepted")
    hot = raw("delhi")
    hot["hourly"]["temperature_2m"] = [99.0] * len(hot["hourly"]["temperature_2m"])
    try:
        weather.parse_open_meteo(hot)
    except ValueError:
        pass
    else:
        raise AssertionError("99 C accepted")
