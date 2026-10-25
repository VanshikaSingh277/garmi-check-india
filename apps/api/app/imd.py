"""IMD district heat warnings (spec §7.1, §9 imd_warnings): our heat level is never shown below IMD's.
Off (IMD_ENABLED) until IMD onboarding. IMD's real response format isn't known here yet, so the only adapter reads
Thandak's own normalised format (below); the real adapter maps IMD's response onto it once access is granted
(docs/launch/imd_access_request.md, TEAM_TODO: IMD district names -> our district ids).

Normalised format: {"issued_at": ISO time, "source_url": str, "warnings": [{"district_id", "date": YYYY-MM-DD,
                    "phenomenon": "heat_wave"|"warm_night"|"hot_humid", "color": "green"|"yellow"|"orange"|"red"}]}"""
import json
from datetime import date, datetime

from sqlalchemy import select

from . import config, db
from .models import ImdWarning

COLORS = ("green", "yellow", "orange", "red")
PHENOMENA = ("heat_wave", "warm_night", "hot_humid")


class ImdProvider:
    name = "base"

    def fetch(self) -> dict:
        raise NotImplementedError


class NormalisedFile(ImdProvider):
    """Reads the normalised format from a file (tests, and a manual import while the real adapter waits)."""
    name = "normalised_file"

    def __init__(self, path: str):
        self.path = path

    def fetch(self) -> dict:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)


_PROVIDER: list[ImdProvider] = []


def set_provider(p: ImdProvider | None):
    _PROVIDER.clear()
    if p:
        _PROVIDER.append(p)


def store(payload: dict) -> dict:
    """Validate and upsert warnings; anything malformed is skipped and counted."""
    ok = bad = 0
    issued = payload.get("issued_at")
    issued_at = datetime.fromisoformat(issued) if isinstance(issued, str) else None
    with db.session() as s:
        for w in payload.get("warnings", []):
            try:
                day = date.fromisoformat(w["date"])
                if w["color"] not in COLORS or w["phenomenon"] not in PHENOMENA or not isinstance(w["district_id"], str):
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                bad += 1
                continue
            s.merge(ImdWarning(district_id=w["district_id"], for_date=day, phenomenon=w["phenomenon"], color=w["color"],
                               issued_at=issued_at, fetched_at=db.utcnow(), source_url=str(payload.get("source_url", ""))[:500]))
            ok += 1
    return {"stored": ok, "skipped": bad}


def run() -> dict:
    if not config.IMD_ENABLED:
        return {"skipped": "IMD_ENABLED is off (waiting for IMD onboarding)"}
    if not _PROVIDER:
        return {"skipped": "no IMD adapter configured yet"}
    return store(_PROVIDER[0].fetch())


def latest_fetch():
    with db.session() as s:
        return s.scalar(select(ImdWarning.fetched_at).order_by(ImdWarning.fetched_at.desc()).limit(1))
