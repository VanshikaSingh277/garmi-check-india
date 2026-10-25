# Phase 1 test results

Run 2026-10-25 15:48 against http://localhost:8000. Cases from `docs/qa/P1_test_cases.md`.

| ID | Title | Result | Notes |
|---|---|---|---|
| P1-01 | Family result still works (browser) | PASS | level=true reasons=3 yourHome=true plan=true fixes=6 errors=none |
| P1-02 | Heat level unchanged by home answers (API) | PASS | levels low/low; home ['tin_roof_top_floor', 'vulnerable_person'] vs [] |
| P1-03 | Outside Delhi: no room numbers, plan still works (API) | PASS | numbers_shown=False, windows=24/24 hours |
| P1-03 | Outside Delhi: no room numbers (browser) | PASS | room number tiles=false; plan shown=true |
| P1-04 | Very hot day uses the offset fallback | PASS | no day above the model's range in October; covered by tests/test_offset_fallback.py (46 C forecast in Delhi -> basis offset) |
| P1-05 | Cooler cards are off (API) | PASS | level=low; shown cooler cards: []; left out: [] |
| P1-05 | Cooler cards are off (browser) | PASS | level=low; cooler card shown=false; left-out line=false (expected only on a Moderate+ day) |
| P1-06 | Only 112 shown by the API | PASS | {"emergency": "112", "ambulance": null, "ambulance_service": null, "ambulance_source": null} |
| P1-07 | No prices without a verified source (API) | PASS | fixes with ₹: []; colony cost: None |
| P1-07 | No prices without a verified source (browser) | PASS | ₹ figure on screen=false |
| P1-08 | Numbers in advice are filled in (API, en + hi) | PASS | placeholders left in: none |
| P1-08 | Numbers in advice are filled in (browser) | PASS | placeholder on screen=false |
| P1-09 | Extra field rejected | PASS | 422 {"error":"invalid_input","message":"Check these fields: surprise"} |
| P1-10 | NaN and out-of-range values | PASS | NaN 422; lat=50 422 |
| P1-11 | Point outside India | PASS | outdoor 422 {'error': 'outside_india', 'message': 'This place is outside India'}; where in_india=False |
| P1-12 | Wrong content type | PASS | 415 |
| P1-13 | Oversized body | PASS | 413, 78012 bytes |
| P1-14 | Unknown values rejected | PASS | [422, 422, 422] |
| P1-15 | Hostile text never 500, never echoed | PASS | [200, 422] |
| P1-16 | Rate limit (runs last: blocks this IP for a minute) | PASS | first 429 at request 276; Retry-After=57 |
| P1-17 | Security headers | PASS | api CSP="default-src 'none'; frame-ancestors 'none'"; site has script hash=True; server header=False |
| P1-18 | Site works under the CSP (browser) | PASS | CSP violations: none; map canvases on last page: 0 |
| P1-19 | Docs routes off | PASS | [404, 404, 404] |
| P1-20 | Tampered data stops prod | PASS | prod start refused: True; RuntimeError: data/ does not match MANIFEST.json: verified_numbers.csv: changed |
| P1-21 | Logs hold no coordinates | PASS | 5 /api/where lines; coordinates or query strings in log: False |
| P1-22 | Weather stale flag | PASS | network cut not simulated live; covered by tests/test_weather_provider.py::test_stale_fallback_up_to_six_hours |
| P1-23 | Hindi parity (browser) | PASS | fixes=6; long English-only lines: none |
| P1-24 | Health and version | PASS | health keys ok=True; version=0.3.0 |

**28 of 28 passed.**
