"""WhatsApp sign-up without the app (spec §6.5). The person messages us first, which proves the number (no OTP).
Steps: PIN code -> consent notice (DRAFT) and "Reply YES" -> language -> alert level. Creates a household
(managed_by=self, 0.1 deg cell from the PIN's gazetteer location), a whatsapp push_target and a consent_event.
Commands at any time: STOP, HELP, ALERT, PIN; YES also answers the retention check."""
import re

from sqlalchemy import select

from engine import areas, districts, places

from . import db, levels, messaging, notify, secure
from .models import ConsentEvent, Household, NoticeLog, PushTarget, WaSession

PIN = re.compile(r"^\d{6}$")
HI_WORDS = {"2", "HI", "HINDI", "हिंदी", "हिन्दी"}
EN_WORDS = {"1", "EN", "ENGLISH"}


def _target(s, ph: str) -> PushTarget | None:
    return s.scalars(select(PushTarget).where(PushTarget.kind == "whatsapp", PushTarget.phone_hmac == ph, PushTarget.active.is_(True))).first()


def _place(pin: str) -> dict | None:
    hit = next((r for r in places.search(pin, 3) if r.get("kind") == "pin" and r.get("pin") == pin), None)
    if not hit:
        return None
    d = districts.district_at(hit["lat"], hit["lon"])
    if not d:
        return None
    in_delhi = 28.40 <= hit["lat"] <= 28.89 and 76.83 <= hit["lon"] <= 77.35 and bool(areas.ward_at(hit["lat"], hit["lon"]))
    return {"lat": round(hit["lat"], 1), "lon": round(hit["lon"], 1), "district_id": d["id"], "district": d["district"],
            "state": d.get("state"), "in_delhi": in_delhi}


def _reply(phone: str, template_id: str, lang: str, **values) -> str:
    text = messaging.render(template_id, lang, emergency="112", **values)
    messaging.provider("whatsapp").send("whatsapp", phone, template_id, notify.no_health(text))
    return template_id


def _delete(s, h: Household):
    s.add(ConsentEvent(household_id=h.id, action="withdrawn", consent_version=h.consent_version, by="self"))
    s.add(ConsentEvent(household_id=h.id, action="deleted", consent_version=h.consent_version, by="self"))
    s.delete(h)


def handle(phone: str, text: str) -> str:
    """Process one inbound message from an already-normalised +91 number. Returns the reply template id."""
    ph = secure.phone_hmac(phone)
    msg = (text or "").strip()
    cmd = msg.upper()
    with db.session() as s:
        t = _target(s, ph)
        h = s.get(Household, t.household_id) if t and t.household_id else None
        if h and t:
            h.last_seen_at = t.last_inbound_at = db.utcnow()   # any reply counts as activity (spec §5.2)
        sess = s.get(WaSession, ph)
        lang = h.lang if h else (sess.data or {}).get("lang", "en") if sess else "en"

        if cmd == "STOP":
            if sess:
                s.delete(sess)
            if not h or not t:
                return _reply(phone, "stop_deleted", lang)
            t.active = False
            others = s.scalars(select(PushTarget).where(PushTarget.household_id == h.id, PushTarget.active.is_(True), PushTarget.id != t.id)).first()
            if others:
                s.add(ConsentEvent(household_id=h.id, action="withdrawn", consent_version=h.consent_version, by="self"))
                return _reply(phone, "stop_kept", lang)
            _delete(s, h)
            return _reply(phone, "stop_deleted", lang)
        if cmd == "HELP":
            return _reply(phone, "help", lang)
        if h and t and cmd == "ALERT":
            lv = levels.today_and_tomorrow(h.cell_lat, h.cell_lon, h.district_id, h.in_delhi)["today"]
            level = lv["level"] if lv else "low"
            text_out = messaging.render("alert_now", lang, level=notify.level_word(level, lang), district=h.district or "")
            s.add(NoticeLog(recipient_key=f"h:{h.id}", target_id=t.id, for_date=db.utcnow().date(), kind="on_request", level=level,
                            channel="whatsapp", template_id="alert_now", lang=lang, text=text_out, status="sent", sent_at=db.utcnow()))
            return _reply(phone, "alert_now", lang, level=notify.level_word(level, lang), district=h.district or "")
        if h and cmd == "YES" and not sess:
            return _reply(phone, "kept", lang, district=h.district or "")
        if h and cmd == "PIN":
            s.merge(WaSession(phone_hmac=ph, step="pin_change", data={"lang": lang}))
            return _reply(phone, "ask_pin", lang)
        if h and sess and sess.step == "pin_change":
            if not PIN.match(msg):
                return _reply(phone, "bad_pin", lang)
            p = _place(msg)
            if not p:
                return _reply(phone, "bad_pin", lang)
            h.cell_lat, h.cell_lon, h.district_id, h.district, h.state = p["lat"], p["lon"], p["district_id"], p["district"], p["state"]
            h.in_delhi = p["in_delhi"]
            s.delete(sess)
            return _reply(phone, "pin_changed", lang, district=p["district"])
        if h:
            return _reply(phone, "help", lang)

        # ---- sign-up
        if not sess:
            s.add(WaSession(phone_hmac=ph, step="pin", data={}))
            return _reply(phone, "ask_pin", lang)
        data = dict(sess.data or {})
        if sess.step == "pin":
            p = _place(msg) if PIN.match(msg) else None
            if not p:
                return _reply(phone, "bad_pin", lang)
            sess.step, sess.data = "consent", {**data, **p}
            return _reply(phone, "consent", lang, district=p["district"])
        if sess.step == "consent":
            if cmd != "YES":
                return _reply(phone, "consent", lang, district=data["district"])
            sess.step = "lang"
            return _reply(phone, "ask_lang", lang)
        if sess.step == "lang":
            if cmd in HI_WORDS or msg in HI_WORDS:
                lang = "hi"
            elif cmd not in EN_WORDS:
                return _reply(phone, "ask_lang", lang)
            sess.step, sess.data = "level", {**data, "lang": lang}
            return _reply(phone, "ask_level", lang)
        if sess.step == "level":
            if cmd not in ("1", "2"):
                return _reply(phone, "ask_level", lang)
            version = messaging.templates()["consent_version"]
            h = Household(lang=lang, cell_lat=data["lat"], cell_lon=data["lon"], district_id=data["district_id"], district=data["district"],
                          state=data["state"], in_delhi=bool(data.get("in_delhi")), alerts_enabled=True,
                          alert_min_level="high" if cmd == "1" else "extreme", managed_by="self",
                          consent_version=version, consent_at=db.utcnow(), consent_by="self")
            s.add(h)
            s.flush()
            enc, kid = secure.encrypt_phone(phone)
            s.add(PushTarget(household_id=h.id, kind="whatsapp", phone_enc=enc, key_id=kid, phone_hmac=ph,
                             verified_via="whatsapp_inbound", last_inbound_at=db.utcnow()))
            s.add(ConsentEvent(household_id=h.id, action="given", consent_version=version, by="self"))
            s.delete(sess)
            return _reply(phone, "signed_up", lang, district=data["district"])
        s.delete(sess)
        return _reply(phone, "ask_pin", lang)
