"""WhatsApp sign-up and webhooks, OTP, push targets (spec §6.5, §6.6, §10.3)."""
import json
import time

from sqlalchemy import select

from app import config, db, secure
from app.models import ConsentEvent, Household, NoticeLog, PushTarget
from engine import weather
from p2_helpers import CLIENT, PHONE, Recorded, fake_sender, home, signed, wa


def test_unsigned_old_or_forged_webhooks_are_rejected():
    body = {"id": "x1", "from": PHONE, "text": "HI"}
    assert CLIENT.post("/api/v1/webhooks/whatsapp", json=body).status_code == 401
    assert signed("/api/v1/webhooks/whatsapp", body, config.WHATSAPP_WEBHOOK_SECRET, ts=int(time.time()) - 600).status_code == 401
    assert signed("/api/v1/webhooks/whatsapp", body, "wrong-secret").status_code == 401


def test_a_repeated_message_id_is_processed_once():
    fake = fake_sender()
    a = wa("HI", phone="+919811100001", msg_id="dup-1")
    b = wa("HI", phone="+919811100001", msg_id="dup-1")
    assert a.json().get("reply") == "ask_pin" and b.json() == {"ok": True, "duplicate": True}
    assert len(fake.sent) == 1


def test_full_whatsapp_sign_up_then_stop_deletes():
    fake = fake_sender()
    weather.set_provider(Recorded("jaisalmer"))
    phone = "+919811100002"
    steps = [("HI", "ask_pin"), ("123", "bad_pin"), ("302001", "consent"), ("maybe", "consent"), ("YES", "ask_lang"),
             ("2", "ask_level"), ("1", "signed_up")]
    for text, want in steps:
        assert wa(text, phone=phone).json()["reply"] == want, text
    ph = secure.phone_hmac(phone)
    with db.session() as s:
        t = s.scalars(select(PushTarget).where(PushTarget.phone_hmac == ph)).one()
        h = s.get(Household, t.household_id)
        assert (h.lang, h.alert_min_level, h.district, h.managed_by, h.alerts_enabled) == ("hi", "high", "Jaipur", "self", True)
        assert (h.cell_lat, h.cell_lon) == (26.9, 75.8)                      # 0.1 deg cell, not the exact point
        assert t.verified_via == "whatsapp_inbound" and t.phone_enc and phone.encode() not in t.phone_enc
        hid = h.id
        assert s.scalars(select(ConsentEvent.action).where(ConsentEvent.household_id == hid)).all() == ["given"]
    assert wa("HELP", phone=phone).json()["reply"] == "help"
    assert wa("ALERT", phone=phone).json()["reply"] == "alert_now"
    assert wa("STOP", phone=phone).json()["reply"] == "stop_deleted"
    with db.session() as s:
        assert s.get(Household, hid) is None
        assert sorted(s.scalars(select(ConsentEvent.action).where(ConsentEvent.household_id == hid)).all()) == ["deleted", "given", "withdrawn"]
    outbox = open(fake.path, encoding="utf-8").read()
    assert phone not in outbox and phone[3:] not in outbox                   # the outbox never holds the number
    assert all("{" not in m["text"] for m in fake.sent)


def test_stop_keeps_the_home_when_another_channel_is_active():
    fake_sender()
    hid, _ = home(phone="+919811100003")
    with db.session() as s:
        enc, kid = secure.encrypt_phone("+919811100004")
        s.add(PushTarget(household_id=hid, kind="sms", phone_enc=enc, key_id=kid, phone_hmac=secure.phone_hmac("+919811100004"), verified_via="otp"))
    assert wa("STOP", phone="+919811100003").json()["reply"] == "stop_kept"
    with db.session() as s:
        assert s.get(Household, hid) is not None


def test_otp_limits_attempts_and_proof():
    fake = fake_sender()
    phone = "+919811100005"
    for _ in range(3):
        assert CLIENT.post("/api/v1/otp/send", json={"phone": phone, "purpose": "household_sms"}).status_code == 200
    r = CLIENT.post("/api/v1/otp/send", json={"phone": phone, "purpose": "household_sms"})
    assert r.status_code == 429 and "retry-after" in r.headers                    # 3 per hour per phone
    code = fake.sent[-1]["text"][:6]
    assert code.isdigit() and code not in json.dumps(r.json())
    for _ in range(5):
        assert CLIENT.post("/api/v1/otp/verify", json={"phone": phone, "code": "000000" if code != "000000" else "111111",
                                                       "purpose": "household_sms"}).status_code == 400
    dead = CLIENT.post("/api/v1/otp/verify", json={"phone": phone, "code": code, "purpose": "household_sms"})
    assert dead.status_code == 400                                                # 6th try: the code is dead


def test_otp_success_gives_a_proof_that_adds_an_sms_target():
    fake = fake_sender()
    phone = "+919811100006"
    CLIENT.post("/api/v1/otp/send", json={"phone": phone, "purpose": "household_sms"})
    code = fake.sent[-1]["text"][:6]
    r = CLIENT.post("/api/v1/otp/verify", json={"phone": phone, "code": code, "purpose": "household_sms"})
    assert r.status_code == 200 and r.json()["proof"]
    _, token = home(phone=None)
    auth = {"Authorization": "Bearer " + token}
    assert CLIENT.post("/api/v1/push", json={"kind": "sms", "phone": phone, "proof": "forged.x"}, headers=auth).status_code == 403
    ok = CLIENT.post("/api/v1/push", json={"kind": "sms", "phone": phone, "proof": r.json()["proof"]}, headers=auth)
    assert ok.status_code == 201 and ok.json()["kind"] == "sms"
    assert CLIENT.post("/api/v1/push", json={"kind": "whatsapp", "phone": phone}, headers=auth).status_code == 422   # only by inbound message


def test_otp_rejects_foreign_numbers_and_respects_the_global_cap():
    assert CLIENT.post("/api/v1/otp/send", json={"phone": "+14155550100", "purpose": "household_sms"}).status_code == 422
    old = config.OTP_DAILY_CAP
    config.OTP_DAILY_CAP = 0
    try:
        r = CLIENT.post("/api/v1/otp/send", json={"phone": "+919811100007", "purpose": "household_sms"})
        assert r.status_code == 503 and r.json()["error"] == "otp_cap"
    finally:
        config.OTP_DAILY_CAP = old


def test_push_targets_belong_to_their_home():
    _, token_a = home(phone=None)
    _, token_b = home(phone=None)
    a = CLIENT.post("/api/v1/push", json={"kind": "fcm", "token": "x" * 40}, headers={"Authorization": "Bearer " + token_a}).json()
    assert CLIENT.delete(f"/api/v1/push/{a['id']}", headers={"Authorization": "Bearer " + token_b}).status_code == 404
    assert CLIENT.delete(f"/api/v1/push/{a['id']}", headers={"Authorization": "Bearer " + token_a}).status_code == 204
    assert CLIENT.post("/api/v1/push", json={"kind": "fcm", "token": "x" * 40}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_push_test_is_limited_to_three_a_day():
    fake_sender()
    _, token = home(phone="+919811100008")
    auth = {"Authorization": "Bearer " + token}
    codes = [CLIENT.post("/api/v1/push/test", json={}, headers=auth).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_notice_opened():
    hid, _ = home(phone="+919811100009")
    with db.session() as s:
        n = NoticeLog(recipient_key=f"h:{hid}", for_date=db.utcnow().date(), kind="test", channel="whatsapp", status="sent")
        s.add(n)
        s.flush()
        nid = n.id
    assert CLIENT.post(f"/api/v1/notices/{nid}/opened", json={}).status_code == 204
    with db.session() as s:
        assert s.get(NoticeLog, nid).status == "opened"
    assert CLIENT.post("/api/v1/notices/not-a-uuid/opened", json={}).status_code == 422
