"""Phase 1 HTTP rules (BACKEND_SPEC §6.1, §6.2, §8.5-8.7, §10.3): limits, error shape, headers, logging, docs, health.
Run from the repo root:  python -m pytest tests"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app import http  # noqa: E402

CLIENT = TestClient(main.app)
HOSTILE = "<script>alert(1)</script>"


def test_docs_routes_are_off_by_default():
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert CLIENT.get(path).status_code == 404, path


def test_api_and_site_security_headers():
    r = CLIENT.get("/api/health")
    assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert "server" not in r.headers
    if main.WEB:
        site = CLIENT.get("/")
        csp = site.headers["content-security-policy"]
        assert site.headers["referrer-policy"] == "strict-origin-when-cross-origin"   # OSM tiles need a Referer
        assert "script-src 'self' 'sha256-" in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_wrong_content_type_is_415():
    r = CLIENT.post("/api/fix_effect", content=b"before=1", headers={"content-type": "text/plain"})
    assert r.status_code == 415 and r.json()["error"] == "unsupported_media_type"


def test_oversized_body_is_413():
    big = json.dumps({"before": [{"indoor_c": 30.0, "outdoor_c": 31.0}] * 2000})
    r = CLIENT.post("/api/fix_effect", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"] == "too_large"


def test_extra_fields_nan_and_unknown_values_are_422():
    base = {"lat": 28.61, "lon": 77.21, "roof": "tin_top"}
    for body in ({**base, "surprise": 1}, {**base, "roof": "mansion"}, {**base, "vulnerable": ["alien"]}, {**base, "lang": "fr"}):
        r = CLIENT.post("/api/status/individual", json=body)
        assert r.status_code == 422 and r.json()["error"] == "invalid_input", body
    r = CLIENT.post("/api/status/individual", content=b'{"lat": NaN, "lon": 77.2, "roof": "tin_top"}',
                    headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_points_outside_india_are_422():
    r = CLIENT.get("/api/outdoor", params={"lat": 10.0, "lon": 70.0})          # Arabian Sea, inside the bounding box
    assert r.status_code == 422 and r.json()["error"] == "outside_india"
    assert CLIENT.get("/api/weather", params={"lat": 50.0, "lon": 77.0}).status_code == 422
    assert CLIENT.get("/api/where", params={"lat": 10.0, "lon": 70.0}).json()["in_india"] is False   # the app says "outside India"


def test_hostile_strings_never_500_and_never_echoed():
    for r in (CLIENT.get("/api/search", params={"q": HOSTILE}),
              CLIENT.post("/api/status/individual", json={"lat": 28.6, "lon": 77.2, "roof": HOSTILE}),
              CLIENT.get("/api/gov/rank", params={"scope": HOSTILE}),
              CLIENT.get("/api/area", params={"lat": 28.6, "lon": 77.2, "lang": HOSTILE})):
        assert r.status_code < 500 and HOSTILE not in r.text


def test_errors_have_the_spec_shape():
    r = CLIENT.get("/api/nothing-here")
    assert r.status_code == 404 and set(r.json()) == {"error", "message"}


def test_rate_limit_returns_429_with_retry_after():
    c = TestClient(http.Guard(main.api, "default-src 'self'", http.RateLimiter(3)))
    codes = [c.get("/api/health").status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
    assert int(c.get("/api/health").headers["retry-after"]) >= 1


def test_access_log_has_no_query_string_or_coordinates():
    lines = []

    class Grab(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())
    h = Grab()
    http.log.addHandler(h)
    try:
        CLIENT.get("/api/where", params={"lat": 28.6139, "lon": 77.2090})
    finally:
        http.log.removeHandler(h)
    line = json.loads(lines[-1])
    assert line["route"] == "/api/where" and line["s"] == 200
    assert "28.6139" not in lines[-1] and "77.209" not in lines[-1] and "lat=" not in lines[-1]


def test_health_and_version_fields():
    h = CLIENT.get("/api/health").json()
    for k in ("ok", "time", "db_ok", "model_loaded", "gazetteer_loaded", "weather_last_ok_at", "weather_provider", "imd_last_ok_at"):
        assert k in h, k
    v = CLIENT.get("/api/version").json()
    assert v["api"] == main.API_VERSION and len(v["rules_sha256"]) == 64 and v["catalogue_version"]


def test_emergency_shows_112_and_no_unverified_ambulance_number():
    e = main.emergency("Delhi")                     # Delhi 102 is seeded but not yet re-checked
    assert e["emergency"] == "112" and e["ambulance"] is None
    assert main.emergency("Nowhere")["ambulance"] is None
