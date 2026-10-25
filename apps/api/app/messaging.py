"""Sending WhatsApp and SMS (spec §4, §6.5). Only the fake provider exists until a provider is chosen and approved
(docs/launch/APPROVALS.md): it writes each message to a local outbox file, never the phone number itself.
A real provider must refuse a template that isn't approved."""
import json
import os
import threading
from datetime import datetime, timezone
from functools import lru_cache

from . import config

TEMPLATES = os.path.join(os.path.dirname(__file__), "..", "data", "message_templates.json")
_lock = threading.Lock()


class SendError(Exception):
    pass


@lru_cache(maxsize=1)
def templates() -> dict:
    with open(TEMPLATES, encoding="utf-8") as f:
        return json.load(f)


def render(template_id: str, lang: str, **values) -> str:
    t = templates()["templates"][template_id]
    return (t.get(lang) or t["en"]).format(**values)


class Provider:
    name = "base"

    def send(self, channel: str, phone: str, template_id: str, text: str) -> str:
        """Send one message; return the provider's message id. Raise SendError on failure."""
        raise NotImplementedError


class FakeProvider(Provider):
    """Writes to <state>/outbox.jsonl: channel, template, text and only the last two digits of the number."""
    name = "fake"

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.STATE_DIR, "outbox.jsonl")
        self.sent: list[dict] = []

    def send(self, channel, phone, template_id, text):
        msg_id = "fake-" + os.urandom(8).hex()
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "id": msg_id, "channel": channel,
               "to": "…" + phone[-2:], "template": template_id, "text": text}
        with _lock:
            self.sent.append({**row, "phone": phone})
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return msg_id


_PROVIDERS: dict = {}


def provider(channel: str) -> Provider:
    name = config.WHATSAPP_PROVIDER if channel == "whatsapp" else config.SMS_PROVIDER
    if name != "fake":
        raise SendError(f"{channel} provider {name!r} is not built yet (only 'fake'; see docs/launch/APPROVALS.md)")
    return _PROVIDERS.setdefault("fake", FakeProvider())


def set_provider(p: Provider | None):
    """For tests and the dry-run script."""
    _PROVIDERS.clear()
    if p:
        _PROVIDERS["fake"] = p


def template_sendable(template_id: str, prov: Provider) -> bool:
    """A real provider may only send approved templates; the fake one sends drafts so the flow can be tested."""
    return prov.name == "fake" or templates()["templates"][template_id]["status"].lower() == "approved"
