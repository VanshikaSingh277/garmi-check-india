"""Shared helpers for the Phase 2 tests: a recorded weather provider, signed webhooks, a fake sender, homes."""
import json
import os
import time

from fastapi.testclient import TestClient

import main
from app import config, db, messaging, secure
from app.models import Household, PushTarget
from engine import weather

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
CLIENT = TestClient(main.app)
PHONE = "+919812345678"


class Recorded(weather.WeatherProvider):
    name = "recorded"

    def __init__(self, fixture="delhi"):
        with open(os.path.join(FIX, f"openmeteo_{fixture}.json"), encoding="utf-8") as f:
            self.data = weather.parse_open_meteo(json.load(f))

    def get(self, lat, lon):
        return self.data


def fake_sender() -> messaging.FakeProvider:
    p = messaging.FakeProvider(os.path.join(config.STATE_DIR, f"outbox-{time.time_ns()}.jsonl"))
    messaging.set_provider(p)
    return p


def signed(path: str, body: dict, secret: str, ts: int | None = None, sig: str | None = None):
    raw = json.dumps(body)
    ts = int(time.time()) if ts is None else ts
    sig = sig or "sha256=" + secure.sign(f"{ts}.{raw}", secret)
    return CLIENT.post(path, content=raw, headers={"content-type": "application/json", "x-thandak-timestamp": str(ts), "x-thandak-signature": sig})


def wa(text: str, phone: str = PHONE, msg_id: str | None = None):
    return signed("/api/v1/webhooks/whatsapp", {"id": msg_id or f"m-{time.time_ns()}", "from": phone, "text": text}, config.WHATSAPP_WEBHOOK_SECRET)


def home(phone: str | None = PHONE, channel: str = "whatsapp", **kw) -> tuple[str, str]:
    """A saved home in Delhi with an app token and (optionally) one phone target. Returns (household id, token)."""
    token = secure.new_token()
    with db.session() as s:
        h = Household(token_hash=secure.token_hash(token), lang=kw.pop("lang", "en"), cell_lat=28.6, cell_lon=77.2, district="New Delhi",
                      state="Delhi", alerts_enabled=True, consent_version="draft-1", consent_by="self", **kw)
        s.add(h)
        s.flush()
        if phone:
            enc, kid = secure.encrypt_phone(phone)
            s.add(PushTarget(household_id=h.id, kind=channel, phone_enc=enc, key_id=kid, phone_hmac=secure.phone_hmac(phone),
                             verified_via="whatsapp_inbound" if channel == "whatsapp" else "otp"))
        return h.id, token
