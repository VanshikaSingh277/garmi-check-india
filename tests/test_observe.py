"""Sentry scrubber (spec §8.8, §10.3): no tokens, phone numbers, coordinates or query strings leave the server."""
import json

from app import observe


def test_scrubber_removes_secrets_phones_tokens_coordinates_and_queries():
    event = {
        "request": {"url": "https://x/api/where?lat=28.6139&lon=77.209", "query_string": "lat=28.6139&lon=77.209",
                    "headers": {"Authorization": "Bearer abc", "Cookie": "s=1", "User-Agent": "ua"}, "data": {"phone": "9812345678"}},
        "user": {"ip_address": "1.2.3.4"},
        "exception": {"values": [{"value": "failed for +91 9812345678 at 28.6139, 77.2090 token ZXhhbXBsZS10b2tlbi10aGF0LWlzLWxvbmctZW5vdWdo"}]},
        "breadcrumbs": {"values": [{"message": "sent to 9812345678"}]},
    }
    out = json.dumps(observe.scrub(event))
    for leak in ("9812345678", "28.6139", "77.2090", "Bearer abc", "s=1", "lat=", "1.2.3.4", "ZXhhbXBsZS10b2tlbi10aGF0"):
        assert leak not in out, leak
    assert "[phone]" in out and "[coords]" in out and "[token]" in out and "User-Agent" in out
