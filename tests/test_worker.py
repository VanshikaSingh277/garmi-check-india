"""Assisted mode (spec §5.3, §5.10, §6.7, §8.4, §10.2 test_worker): isolation across workers and orgs, access_log
rows, reassignment, deactivation, OTP sign-in without number probing, encryption at rest, briefs without health details."""
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import admin, db, jobs, workers
from app.models import AccessLog, Household, NoticeLog, Worker, WorkerSession
from engine import weather
from p2_helpers import CLIENT, Recorded, fake_sender

PLACE = {"lat": 28.6139, "lon": 77.2090}
CONSENT = {"version": "draft-1", "by": "worker", "script_version": "draft-1"}
PEOPLE = [{"age_band": "older_75_plus", "nickname": "Dadi", "conditions": ["heart"], "medicine_classes": ["water_pill"], "lives_alone": True},
          {"age_band": "infant_0_1", "nickname": "Munni"}]


def login(phone: str) -> str:
    fake = fake_sender()
    assert CLIENT.post("/api/v1/otp/send", json={"phone": phone, "purpose": "worker_login"}).status_code == 200
    code = fake.sent[-1]["text"][:6]
    r = CLIENT.post("/api/v1/otp/verify", json={"phone": phone, "code": code, "purpose": "worker_login"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(token):
    return {"Authorization": "Bearer " + token}


def setup_orgs(tag: str):
    weather.set_provider(Recorded("delhi"))
    org1 = admin.create_org(f"NGO {tag} one", "ngo", "Delhi", None)
    org2 = admin.create_org(f"NGO {tag} two", "ngo", "Delhi", None)
    admin.invite_admin(org1, "Admin One", f"+919770{tag}0001")
    admin.invite_admin(org2, "Admin Two", f"+919770{tag}0002")
    a1, a2 = login(f"+919770{tag}0001"), login(f"+919770{tag}0002")
    for name, ph, tok, org in (("Asha A", "0011", a1, org1), ("Asha B", "0012", a1, org1), ("Asha C", "0013", a2, org2)):
        r = CLIENT.post(f"/api/v1/orgs/{org}/workers", json={"display_name": name, "phone": f"+919770{tag}{ph}", "role": "asha"}, headers=H(tok))
        assert r.status_code == 201, r.text
    return org1, org2, a1, a2, login(f"+919770{tag}0011"), login(f"+919770{tag}0012"), login(f"+919770{tag}0013")


def test_isolation_access_log_reassignment_and_deactivation():
    org1, org2, a1, a2, wa, wb, wc = setup_orgs("11")
    r = CLIENT.post("/api/v1/workers/me/households", json={"consent": CONSENT, "lang": "hi", "place": PLACE, "home": {"roof": "tin_top"},
                                                           "people": PEOPLE}, headers=H(wa))
    assert r.status_code == 201, r.text
    hid = r.json()["household_id"]
    # other workers in the same org and in another org see nothing
    for tok in (wb, wc, a2):
        assert CLIENT.patch(f"/api/v1/workers/me/households/{hid}", json={"lang": "en"}, headers=H(tok)).status_code == 404
        assert CLIENT.delete(f"/api/v1/workers/me/households/{hid}", headers=H(tok)).status_code == 404
        assert hid not in str(CLIENT.get("/api/v1/workers/me/households", headers=H(tok)).json())
    # an admin of another org can't reassign it
    wid_b = CLIENT.get("/api/v1/workers/me", headers=H(wb)).json()["worker_id"]
    assert CLIENT.patch(f"/api/v1/orgs/{org2}/households/{hid}", json={"worker_id": wid_b}, headers=H(a2)).status_code == 404
    assert CLIENT.patch(f"/api/v1/orgs/{org1}/households/{hid}", json={"worker_id": wid_b}, headers=H(wa)).status_code == 404   # not an admin
    listed = CLIENT.get("/api/v1/workers/me/households", headers=H(wa)).json()["households"]
    assert [x["household_id"] for x in listed] == [hid]
    assert CLIENT.get("/api/v1/workers/me/brief?format=text", headers=H(wa)).status_code == 200
    assert CLIENT.patch(f"/api/v1/workers/me/households/{hid}", json={"home": {"fan": True}}, headers=H(wa)).status_code == 200
    # the org admin reassigns it when a worker leaves
    assert CLIENT.patch(f"/api/v1/orgs/{org1}/households/{hid}", json={"worker_id": wid_b}, headers=H(a1)).status_code == 200
    assert CLIENT.patch(f"/api/v1/workers/me/households/{hid}", json={"lang": "en"}, headers=H(wa)).status_code == 404
    assert CLIENT.patch(f"/api/v1/workers/me/households/{hid}", json={"lang": "en"}, headers=H(wb)).status_code == 200
    with db.session() as s:
        wid_a = s.scalars(select(Worker.id).where(Worker.display_name == "Asha A")).first()
        acts = sorted(set(s.scalars(select(AccessLog.action).where(AccessLog.household_id == hid, AccessLog.worker_id == wid_a)).all()))
    assert acts == ["brief", "create", "edit", "view"], acts
    # deactivating a worker revokes every session
    assert CLIENT.patch(f"/api/v1/orgs/{org1}/workers/{wid_a}", json={"active": False}, headers=H(a1)).status_code == 200
    assert CLIENT.get("/api/v1/workers/me", headers=H(wa)).status_code == 401
    assert CLIENT.delete(f"/api/v1/workers/me/households/{hid}", headers=H(wb)).status_code == 204
    with db.session() as s:
        assert s.get(Household, hid) is None
        assert "delete" in s.scalars(select(AccessLog.action).where(AccessLog.household_id == hid)).all()


def test_people_are_encrypted_at_rest_and_never_in_the_brief_text():
    *_, wa, _, _ = setup_orgs("22")
    hid = CLIENT.post("/api/v1/workers/me/households", json={"consent": CONSENT, "place": PLACE, "people": PEOPLE}, headers=H(wa)).json()["household_id"]
    con = sqlite3.connect(db.engine.url.database)
    dump = "\n".join(con.iterdump())
    con.close()
    for secret in ("Dadi", "Munni", "heart", "water_pill"):
        assert secret not in dump, secret
    with db.session() as s:
        got = workers.load_people(s, s.get(Household, hid))
    assert got[0]["nickname"] == "Dadi" and got[0]["conditions"] == ["heart"] and got[0]["medicine_classes"] == ["water_pill"]
    rows = [{"household_id": hid, "district": "New Delhi", "ward_no": "12", "level_index": 2,
             "persons_at_risk": [{"person": 0, "label": "Dadi", "age_band": "older_75_plus", "why": ["older", "condition", "medicine"]}],
             "actions": [{"code": "medicine_doctor", "text": "Dadi takes water-pill (diuretic) medicines: don't stop them."},
                         {"code": "check_on_alone", "text": "Dadi lives alone: call or visit more than once today."}]}]
    text = workers.brief_text(rows, "tomorrow", "en")
    assert "Dadi" in text and "diuretic" not in text and "medicine" not in text and "heart" not in text
    rows[0]["persons_at_risk"][0]["label"] = "Heart Dadi"                  # a nickname with a health word in it
    rows[0]["actions"][1]["text"] = "Heart Dadi lives alone: call or visit more than once today."
    text = workers.brief_text(rows, "tomorrow", "en")
    assert "Heart" not in text and "The older person" in text


def test_sign_in_never_reveals_whether_a_number_is_a_worker():
    fake = fake_sender()
    a = CLIENT.post("/api/v1/otp/send", json={"phone": "+919779999999", "purpose": "worker_login"})
    assert a.status_code == 200 and a.json() == {"sent": True, "expires_in_s": 600} and not fake.sent
    r = CLIENT.post("/api/v1/otp/verify", json={"phone": "+919779999999", "code": "123456", "purpose": "worker_login"})
    assert r.status_code == 400


def test_admin_sessions_are_short_and_worker_sessions_long():
    org = admin.create_org("NGO 33", "ngo", "Delhi", None)
    admin.invite_admin(org, "Admin", "+919773300001")
    login("+919773300001")
    with db.session() as s:
        w = s.scalars(select(Worker).where(Worker.display_name == "Admin", Worker.org_id == org)).one()
        sess = s.scalars(select(WorkerSession).where(WorkerSession.worker_id == w.id)).one()
        assert timedelta(hours=11) < sess.expires_at - sess.created_at <= timedelta(hours=12)


def test_bad_worker_requests():
    *_, wa, _, _ = setup_orgs("44")
    base = {"consent": CONSENT, "place": PLACE, "people": PEOPLE}
    assert CLIENT.post("/api/v1/workers/me/households", json={**base, "consent": {**CONSENT, "script_version": "old"}}, headers=H(wa)).status_code == 409
    assert CLIENT.post("/api/v1/workers/me/households", json={**base, "people": []}, headers=H(wa)).status_code == 422
    assert CLIENT.post("/api/v1/workers/me/households", json={**base, "people": [{"age_band": "adult_15_64", "name": "Ravi Kumar"}]}, headers=H(wa)).status_code == 422
    assert CLIENT.post("/api/v1/workers/me/households", json=base).status_code == 401
    assert CLIENT.post("/api/v1/orgs/not-a-uuid/workers", json={"display_name": "X", "phone": "+919000000000", "role": "asha"}, headers=H(wa)).status_code == 422


def test_worker_brief_job_and_retention():
    *_, wa, _, _ = setup_orgs("55")
    CLIENT.post("/api/v1/workers/me/households", json={"consent": CONSENT, "place": PLACE, "people": PEOPLE}, headers=H(wa))
    real = workers.levels.day_level
    workers.levels.day_level = lambda *a, **k: {"level": "high", "level_index": 2, "reasons": []}
    try:
        out = jobs.worker_brief(datetime(2026, 5, 19, 19, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    finally:
        workers.levels.day_level = real
    assert out["queued"] >= 1
    with db.session() as s:
        n = s.scalars(select(NoticeLog).where(NoticeLog.kind == "worker_brief")).first()
        assert n.recipient_key.startswith("w:") and "medicine" not in n.text and "heart" not in n.text
        s.add(AccessLog(worker_id="old", household_id="old", action="view", at=db.utcnow() - timedelta(days=400)))
    assert jobs.retention_purge()["access_logs"] >= 1
