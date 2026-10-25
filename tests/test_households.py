"""Saved households and app/browser push (spec §6.3, §6.5, §8.2, §10.2 test_households)."""
import base64
import json
import sqlite3
from contextlib import contextmanager

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from sqlalchemy import select

from app import config, db, households, http, jobs, push
from app.models import ConsentEvent, Household, NoticeLog, PushTarget
from engine import weather
from p2_helpers import CLIENT, Recorded, home

NEW = {"consent": {"version": "draft-1", "accepted": True}, "lang": "en", "place": {"lat": 28.6139, "lon": 77.2090},
       "home": {"roof": "tin_top", "fan": True, "power_cut_hours": [["14:00", "16:00"]]},
       "summary": {"higher_risk": True, "share_counts": False, "counts": {"older": 1}}, "alerts": {"enabled": True, "hour_ist": 19, "min_level": "high"}}


@contextmanager
def on():
    old = config.HOUSEHOLDS_ENABLED
    config.HOUSEHOLDS_ENABLED = True
    weather.set_provider(Recorded("delhi"))
    try:
        yield
    finally:
        config.HOUSEHOLDS_ENABLED = old


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_off_until_the_frontend_prerequisite_is_done():
    assert config.HOUSEHOLDS_ENABLED is False
    r = CLIENT.post("/api/v1/households", json=NEW)
    assert r.status_code == 404 and r.json()["error"] == "not_enabled"


def test_create_stores_the_cell_not_the_gps_and_counts_only_when_shared():
    with on():
        r = CLIENT.post("/api/v1/households", json=NEW)
        assert r.status_code == 201
        hid, token = r.json()["household_id"], r.json()["token"]
        con = sqlite3.connect(db.engine.url.database)
        dump = "\n".join(con.iterdump())
        con.close()
        assert "28.6139" not in dump and "77.209" not in dump and token not in dump
        me = CLIENT.get("/api/v1/households/me", headers=auth(token)).json()
        assert me["cell"] == {"lat": 28.6, "lon": 77.2} and me["summary"]["counts"] is None and me["summary"]["higher_risk"] is True
        assert not {"lat", "lon", "gps"} & set(me["home"])
        with db.session() as s:
            assert s.scalars(select(ConsentEvent.action).where(ConsentEvent.household_id == hid)).all() == ["given"]
        shared = CLIENT.post("/api/v1/households", json={**NEW, "summary": {**NEW["summary"], "share_counts": True}}).json()
        assert CLIENT.get("/api/v1/households/me", headers=auth(shared["token"])).json()["summary"]["counts"]["older"] == 1


def test_bad_requests():
    with on():
        assert CLIENT.post("/api/v1/households", json={**NEW, "consent": {"version": "old", "accepted": True}}).status_code == 409
        assert CLIENT.post("/api/v1/households", json={**NEW, "consent": {"version": "draft-1", "accepted": False}}).status_code == 422
        assert CLIENT.post("/api/v1/households", json={**NEW, "place": {"lat": 10.0, "lon": 70.0}}).json()["error"] == "outside_india"
        assert CLIENT.post("/api/v1/households", json={**NEW, "gps": [28.6, 77.2]}).status_code == 422
        assert CLIENT.post("/api/v1/households", json={**NEW, "summary": {"higher_risk": True, "conditions": ["heart"]}}).status_code == 422
        assert CLIENT.get("/api/v1/households/me").status_code == 401


def test_patch_export_rotate_delete():
    with on():
        token = CLIENT.post("/api/v1/households", json=NEW).json()["token"]
        p = CLIENT.patch("/api/v1/households/me", json={"place": {"lat": 26.91, "lon": 75.79}, "home": {"ac": True}}, headers=auth(token)).json()
        assert p["cell"] == {"lat": 26.9, "lon": 75.8} and p["district"] == "Jaipur" and p["home"]["ac"] is True and p["home"]["roof"] == "tin_top"
        hid = p["household_id"]
        with db.session() as s:
            from app import secure
            enc, kid = secure.encrypt_phone("+919833300001")
            s.add(PushTarget(household_id=hid, kind="sms", phone_enc=enc, key_id=kid, phone_hmac=secure.phone_hmac("+919833300001"), verified_via="otp"))
        ex = CLIENT.get("/api/v1/households/me/export", headers=auth(token))
        assert ex.status_code == 200 and "9833300001" not in ex.text and "…01" in ex.text
        new = CLIENT.post("/api/v1/households/me/token/rotate", json={}, headers=auth(token)).json()["token"]
        assert CLIENT.get("/api/v1/households/me", headers=auth(token)).status_code == 401
        assert CLIENT.get("/api/v1/households/me", headers=auth(new)).status_code == 200
        assert CLIENT.delete("/api/v1/households/me", headers=auth(new)).status_code == 204
        with db.session() as s:
            assert s.get(Household, hid) is None
            assert not s.scalars(select(PushTarget).where(PushTarget.household_id == hid)).all()
            assert sorted(s.scalars(select(ConsentEvent.action).where(ConsentEvent.household_id == hid)).all()) == ["deleted", "exported", "given"]
        assert CLIENT.get("/api/v1/households/me", headers=auth(new)).status_code == 401


def test_status_and_outlook_use_the_saved_home_and_people_from_the_phone():
    with on():
        token = CLIENT.post("/api/v1/households", json=NEW).json()["token"]
        st = CLIENT.post("/api/v1/households/me/status", json={"day": "today", "people": [{"age_band": "older_65_74", "nickname": "Dadi"}]}, headers=auth(token))
        assert st.status_code == 200 and st.json()["per_person"][0]["label"] == "Dadi" and "calibration" in st.json()
        assert st.json()["fan"]["group"] == "older"
        ol = CLIENT.post("/api/v1/households/me/outlook", json={"days": 7, "people": [{"age_band": "older_65_74"}]}, headers=auth(token)).json()["days"]
        assert 1 <= len(ol) <= 7 and {"date", "level", "reasons", "hi_max", "tmax", "tmin", "twb_max", "persons_at_risk"} <= set(ol[0])
        assert "room_peak_range" in ol[0]                                         # Delhi: room numbers allowed
        assert CLIENT.post("/api/v1/households/me/outlook", json={"days": 8}, headers=auth(token)).status_code == 422
        with db.session() as s:                                                  # nothing about the people was stored
            dump = json.dumps([str(h.__dict__) for h in s.scalars(select(Household)).all()])
        assert "Dadi" not in dump and "older_65_74" not in dump


def test_new_homes_are_rate_limited_per_ip():
    with on():
        old = households.NEW_LIMIT
        households.NEW_LIMIT = http.RateLimiter(2, 3600)
        try:
            codes = [CLIENT.post("/api/v1/households", json=NEW).status_code for _ in range(3)]
        finally:
            households.NEW_LIMIT = old
        assert codes == [201, 201, 429]


def test_web_push_endpoints_must_be_real_push_services():
    _, token = home(phone=None)
    keys = {"p256dh": "x" * 87, "auth": "y" * 22}
    for bad in ("https://evil.example.com/x", "http://fcm.googleapis.com/fcm/send/abc", "https://fcm.googleapis.com.evil.io/x"):
        r = CLIENT.post("/api/v1/push", json={"kind": "webpush", "endpoint": bad, "keys": keys}, headers=auth(token))
        assert r.status_code == 422, bad
    ok = CLIENT.post("/api/v1/push", json={"kind": "webpush", "endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": keys}, headers=auth(token))
    assert ok.status_code == 201


def test_push_notices_are_sent_and_unsubscribed_devices_switched_off():
    hid, _ = home(phone=None)
    with db.session() as s:
        t = PushTarget(household_id=hid, kind="fcm", fcm_token="tok-" + "a" * 30)
        s.add(t)
        s.flush()
        tid = t.id
        s.add(NoticeLog(recipient_key=f"h:{hid}", target_id=tid, for_date=db.utcnow().date(), kind="test", channel="fcm",
                        template_id="test_alert", lang="hi", text="ठंडक: यह एक टेस्ट अलर्ट है।", status="queued"))
    fake = push.FakePush()
    push.set_sender("fcm", fake)
    config.ALERTS_ENABLED_GLOBAL = True
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        jobs.send_queue(datetime(2026, 5, 20, 19, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
        assert fake.sent and fake.sent[-1]["title"] == "ठंडक" and "token" not in json.dumps(fake.sent)

        class Unsubscribed(push.PushSender):
            name = "fake"                 # a real sender would first refuse the DRAFT template (checked elsewhere)

            def send(self, target, title, body, notice_id):
                raise push.Gone("unregistered")
        push.set_sender("fcm", Unsubscribed())
        with db.session() as s:
            s.add(NoticeLog(recipient_key=f"h:{hid}", target_id=tid, for_date=db.utcnow().date(), kind="evening", channel="fcm",
                            template_id="evening_alert", lang="en", text="Thandak: Tomorrow, High heat in X.", status="queued"))
        jobs.send_queue(datetime(2026, 5, 20, 19, 5, tzinfo=ZoneInfo("Asia/Kolkata")))
        with db.session() as s:
            assert s.get(PushTarget, tid).active is False
    finally:
        config.ALERTS_ENABLED_GLOBAL = False
        push.set_sender("fcm", None)


def test_web_push_encryption_matches_rfc_8291():
    asp = ec.derive_private_key(int.from_bytes(push.unb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    out = push.encrypt(push.unb64u("V2hlbiBJIGdyb3cgdXAsIEkgd2FudCB0byBiZSBhIHdhdGVybWVsb24"),
                       push.unb64u("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"),
                       push.unb64u("BTBZMqHH6r4Tts7J_aSIgg"), as_private=asp, salt=push.unb64u("DGv6ra1nlYgDCS1FRnbzlw"))
    assert push.b64u(out) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A"
                              "_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_vapid_header_is_a_valid_es256_jwt():
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    old = (config.VAPID_PRIVATE_KEY, config.VAPID_PUBLIC_KEY, config.VAPID_SUBJECT)
    config.VAPID_PRIVATE_KEY = push.b64u(key.private_numbers().private_value.to_bytes(32, "big"))
    config.VAPID_PUBLIC_KEY, config.VAPID_SUBJECT = push.b64u(pub), "mailto:test@example.org"
    try:
        h = push.vapid_header("https://fcm.googleapis.com/fcm/send/abc", now=1_700_000_000)
        jwt = h.split("t=")[1].split(",")[0]
        head, claims, sig = jwt.split(".")
        assert json.loads(push.unb64u(claims)) == {"aud": "https://fcm.googleapis.com", "exp": 1_700_000_000 + push.TTL_S, "sub": "mailto:test@example.org"}
        raw = push.unb64u(sig)
        key.public_key().verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                                f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    finally:
        config.VAPID_PRIVATE_KEY, config.VAPID_PUBLIC_KEY, config.VAPID_SUBJECT = old


def test_fcm_signs_a_token_request_and_sends_the_message():
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    fcm = push.Fcm({"client_email": "svc@proj.iam.gserviceaccount.com", "private_key": pem, "project_id": "proj"})
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        req = httpx.Request("POST", url)
        if url == push.GOOGLE_OAUTH_ENDPOINT:
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600}, request=req)
        return httpx.Response(200, json={"name": "projects/proj/messages/1"}, request=req)
    orig = push.httpx.post
    push.httpx.post = fake_post
    try:
        t = PushTarget(kind="fcm", fcm_token="device-token")
        assert fcm.send(t, "Thandak", "Tomorrow: High heat.", "n1") == "projects/proj/messages/1"
    finally:
        push.httpx.post = orig
    assert calls[0][0] == push.GOOGLE_OAUTH_ENDPOINT and calls[1][0].endswith("/projects/proj/messages:send")
    assert calls[1][1]["json"]["message"]["token"] == "device-token" and calls[1][1]["headers"]["Authorization"] == "Bearer at"
    assertion = calls[0][1]["data"]["assertion"]
    head, claims, sig = assertion.split(".")
    from cryptography.hazmat.primitives.asymmetric import padding
    rsa_key.public_key().verify(base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    try:
        push.Fcm({"client_email": "x", "private_key": pem, "project_id": "p", "token_uri": "https://evil.example.com/token"})
    except push.SendError:
        pass
    else:
        raise AssertionError("a foreign token_uri must be refused")
