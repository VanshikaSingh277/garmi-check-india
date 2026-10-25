"""New endpoints (spec §6.5, §6.6, §6.9). Locations only in POST bodies; tokens compared as hashes; errors are
{"error", "message"}; phone numbers are never returned, logged or echoed.

Webhook signing (until a provider is chosen, then its adapter maps onto this): headers
  X-Thandak-Timestamp: unix seconds   X-Thandak-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>
Older than 5 minutes is rejected; a repeated message id is processed once."""
import base64
import json
import secrets
import time
from datetime import timedelta
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response
from pydantic import Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import config, db, http, jobs, messaging, notify, observe, push, secure, whatsapp
from .models import ConsentEvent, Household, InboundMessage, NoticeLog, Otp, PushTarget, Worker
from .schemas import Problem, Strict

router = APIRouter()
internal = APIRouter()
TOKEN_LIMIT = http.RateLimiter(120)          # authenticated routes: 120/min per token (spec §8.7)
TEST_LIMIT = http.RateLimiter(config.PUSH_TEST_PER_DAY, 86400)
UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


Phone = Annotated[str, StringConstraints(min_length=10, max_length=16)]


def _need(*names: str):
    gone = config.missing(*names)
    if gone:
        raise Problem(503, "not_configured", "This feature isn't set up on this server")


def _phone(raw: str) -> str:
    p = secure.normalise_phone(raw)
    if not p:
        raise Problem(422, "invalid_phone", "Indian mobile numbers (+91) only")
    return p


# ------------------------------------------------------------------ auth
def household(request: Request, authorization: Optional[str] = Header(None)) -> str:
    """The household id behind a Bearer token (constant-time hash comparison through the unique index)."""
    _need("TOKEN_PEPPER")
    if not authorization or not authorization.startswith("Bearer "):
        raise Problem(401, "unauthorized", "Missing token")
    th = secure.token_hash(authorization[7:].strip())
    ok, retry = TOKEN_LIMIT.check("t:" + th)
    if not ok:
        raise Problem(429, "rate_limited", "Too many requests", {"Retry-After": str(retry)})
    with db.session() as s:
        h = s.scalars(select(Household).where(Household.token_hash == th, Household.deleted_at.is_(None))).first()
        if not h or not secure.same(h.token_hash or "", th):
            http.token_failed(request)
            raise Problem(401, "unauthorized", "Unknown token")
        h.last_seen_at = db.utcnow()
        return h.id


# ------------------------------------------------------------------ webhooks
async def _signed(request: Request, secret: str) -> dict:
    ts, sig = request.headers.get("x-thandak-timestamp", ""), request.headers.get("x-thandak-signature", "")
    body = (await request.body()).decode("utf-8", "replace")
    if not ts.isdigit() or abs(time.time() - int(ts)) > config.WA_WINDOW_S:
        raise Problem(401, "stale_or_unsigned", "Webhook too old or not signed")
    if not secure.same(sig, "sha256=" + secure.sign(f"{ts}.{body}", secret)):
        raise Problem(401, "bad_signature", "Signature check failed")
    try:
        data = json.loads(body)
    except ValueError:
        raise Problem(422, "invalid_input", "Body is not JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not 0 < len(data["id"]) <= 80:
        raise Problem(422, "invalid_input", "Missing message id")
    return data


def _first_time(msg_id: str, channel: str) -> bool:
    try:
        with db.session() as s:
            s.add(InboundMessage(provider_msg_id=msg_id, channel=channel))
        return True
    except IntegrityError:
        return False


@router.post("/api/v1/webhooks/whatsapp")
async def webhook_whatsapp(request: Request):
    _need("WHATSAPP_WEBHOOK_SECRET", "PHONE_HMAC_KEY", "PHONE_ENC_KEYS", "TOKEN_PEPPER")
    data = await _signed(request, config.WHATSAPP_WEBHOOK_SECRET)
    if not _first_time(data["id"], "whatsapp"):
        return {"ok": True, "duplicate": True}
    phone = secure.normalise_phone(str(data.get("from", "")))
    text = data.get("text")
    if not phone or not isinstance(text, str) or len(text) > 500:
        return {"ok": True, "ignored": True}            # not an Indian mobile or not a text message
    from starlette.concurrency import run_in_threadpool
    reply = await run_in_threadpool(whatsapp.handle, phone, text)
    return {"ok": True, "reply": reply}


@router.post("/api/v1/webhooks/sms-status")
async def webhook_sms_status(request: Request):
    _need("SMS_WEBHOOK_SECRET")
    data = await _signed(request, config.SMS_WEBHOOK_SECRET)
    if not _first_time(data["id"], "sms"):
        return {"ok": True, "duplicate": True}
    status = data.get("status")
    if status not in ("delivered", "failed") or not isinstance(data.get("provider_msg_id"), str):
        return {"ok": True, "ignored": True}
    with db.session() as s:
        n = s.scalars(select(NoticeLog).where(NoticeLog.provider_msg_id == data["provider_msg_id"])).first()
        if n and status == "failed":
            n.status, n.error = "failed", "provider_reported_failure"
    return {"ok": True}


# ------------------------------------------------------------------ OTP (SMS in Phase 2; workers in Phase 5)
class OtpSend(Strict):
    phone: Phone
    purpose: Literal["household_sms", "worker_login"]


class OtpVerify(Strict):
    phone: Phone
    code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
    purpose: Literal["household_sms", "worker_login"]


@router.post("/api/v1/otp/send")
def otp_send(q: OtpSend, request: Request):
    _need("TOKEN_PEPPER", "PHONE_HMAC_KEY")
    phone = _phone(q.phone)
    ph, iph = secure.phone_hmac(phone), secure.ip_hash(http.client_ip(request.scope))
    now = db.utcnow()
    with db.session() as s:
        def n(*conds):
            return s.scalar(select(func.count()).select_from(Otp).where(*conds)) or 0
        if n(Otp.created_at >= now - timedelta(days=1)) >= config.OTP_DAILY_CAP:
            observe.log.warning("OTP daily cap reached")
            raise Problem(503, "otp_cap", "Codes are paused for today; please try later")
        if (n(Otp.phone_hmac == ph, Otp.created_at >= now - timedelta(hours=1)) >= config.OTP_PER_PHONE_HOUR
                or n(Otp.phone_hmac == ph, Otp.created_at >= now - timedelta(days=1)) >= config.OTP_PER_PHONE_DAY
                or n(Otp.ip_hash == iph, Otp.created_at >= now - timedelta(days=1)) >= config.OTP_PER_IP_DAY):
            raise Problem(429, "rate_limited", "Too many codes; please try later", {"Retry-After": "3600"})
        code = f"{secrets.randbelow(10 ** 6):06d}"
        s.add(Otp(phone_hmac=ph, purpose=q.purpose, code_hash=secure.code_hash(code, ph), ip_hash=iph,
                  expires_at=now + timedelta(minutes=config.OTP_TTL_MIN)))
        # worker sign-in: the same answer whether or not the number is a worker, so numbers can't be probed
        is_worker = q.purpose != "worker_login" or s.scalars(select(Worker).where(Worker.phone_hmac == ph, Worker.active.is_(True))).first() is not None
    if is_worker:
        text = messaging.render("otp", "en", code=code, minutes=config.OTP_TTL_MIN)
        try:
            messaging.provider("sms").send("sms", phone, "otp", text)
        except messaging.SendError:
            raise Problem(503, "sms_unavailable", "SMS isn't available right now") from None
    return {"sent": True, "expires_in_s": config.OTP_TTL_MIN * 60}


def _proof(ph: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"ph": ph, "exp": int(time.time()) + config.SMS_PROOF_TTL_MIN * 60}).encode()).decode()
    return body + "." + secure.sign(body, config.TOKEN_PEPPER)


def _proof_ok(proof: str, ph: str) -> bool:
    body, _, sig = proof.partition(".")
    if not body or not secure.same(sig, secure.sign(body, config.TOKEN_PEPPER)):
        return False
    try:
        d = json.loads(base64.urlsafe_b64decode(body.encode()))
    except ValueError:
        return False
    return d.get("ph") == ph and d.get("exp", 0) >= time.time()


@router.post("/api/v1/otp/verify")
def otp_verify(q: OtpVerify):
    _need("TOKEN_PEPPER", "PHONE_HMAC_KEY")
    ph = secure.phone_hmac(_phone(q.phone))
    good = False
    with db.session() as s:                           # the attempt is committed before any error is raised
        o = s.scalars(select(Otp).where(Otp.phone_hmac == ph, Otp.purpose == q.purpose, Otp.consumed_at.is_(None),
                                        Otp.expires_at >= db.utcnow()).order_by(Otp.created_at.desc())).first()
        if o:
            o.attempts += 1
            if o.attempts > config.OTP_MAX_ATTEMPTS:
                o.consumed_at = db.utcnow()           # dead after 5 tries
            elif secure.same(o.code_hash, secure.code_hash(q.code, ph)):
                o.consumed_at, good = db.utcnow(), True
    if not good:
        raise Problem(400, "invalid_code", "Code not valid")
    if q.purpose == "worker_login":
        from . import workers
        with db.session() as s:
            w = s.scalars(select(Worker).where(Worker.phone_hmac == ph, Worker.active.is_(True))).first()
            if not w:
                raise Problem(400, "invalid_code", "Code not valid")
            token = workers.new_session(s, w)
            life = config.ADMIN_SESSION_HOURS * 3600 if w.role == "org_admin" else config.WORKER_SESSION_DAYS * 86400
            return {"token": token, "role": w.role, "expires_in_s": life}
    return {"proof": _proof(ph), "expires_in_s": config.SMS_PROOF_TTL_MIN * 60}


# ------------------------------------------------------------------ push targets
class WebPushKeys(Strict):
    p256dh: Annotated[str, StringConstraints(max_length=200)]
    auth: Annotated[str, StringConstraints(max_length=100)]


class PushFcm(Strict):
    kind: Literal["fcm"]
    token: Annotated[str, StringConstraints(min_length=20, max_length=4096)]


class PushWeb(Strict):
    kind: Literal["webpush"]
    endpoint: Annotated[str, StringConstraints(pattern=r"^https://", max_length=1000)]
    keys: WebPushKeys


class PushSms(Strict):
    kind: Literal["sms"]
    phone: Phone
    proof: Annotated[str, StringConstraints(max_length=400)]


PushIn = Annotated[Union[PushFcm, PushWeb, PushSms], Field(discriminator="kind")]


@router.post("/api/v1/push", status_code=201)
def push_add(t: Annotated[PushIn, Body()], hid: str = Depends(household)):
    with db.session() as s:
        if isinstance(t, PushSms):
            _need("PHONE_ENC_KEYS", "PHONE_HMAC_KEY")
            phone = _phone(t.phone)
            ph = secure.phone_hmac(phone)
            if not _proof_ok(t.proof, ph):
                raise Problem(403, "otp_required", "Verify the number with a code first")
            enc, kid = secure.encrypt_phone(phone)
            row = PushTarget(household_id=hid, kind="sms", phone_enc=enc, key_id=kid, phone_hmac=ph, verified_via="otp")
        elif isinstance(t, PushWeb) and not push.endpoint_ok(t.endpoint):
            raise Problem(422, "push_endpoint", "Not a known push service")
        elif isinstance(t, PushFcm):
            row = PushTarget(household_id=hid, kind="fcm", fcm_token=t.token)
        else:
            row = PushTarget(household_id=hid, kind="webpush", endpoint=t.endpoint, p256dh=t.keys.p256dh, auth=t.keys.auth)
        s.add(row)
        s.flush()
        return {"id": row.id, "kind": row.kind}


@router.delete("/api/v1/push/{target_id}", status_code=204)
def push_delete(target_id: Annotated[str, Path(pattern=UUID)], hid: str = Depends(household)):
    with db.session() as s:
        t = s.get(PushTarget, target_id)
        if not t or t.household_id != hid:
            raise Problem(404, "not_found", "Not found")
        s.delete(t)
    return Response(status_code=204)


@router.post("/api/v1/push/test")
def push_test(hid: str = Depends(household)):
    """At most 3 presses a day. notice_log's unique key keeps one test row per channel per day, so a repeat press
    re-queues nothing new (spec §5.9 vs §6.5)."""
    ok, retry = TEST_LIMIT.check("test:" + hid)
    if not ok:
        raise Problem(429, "rate_limited", "Three test alerts a day", {"Retry-After": str(retry)})
    today = db.utcnow().date()
    with db.session() as s:
        h = s.get(Household, hid)
        n = sum(notify.queue(s, h, t, today, "test", None, "test_alert", messaging.render("test_alert", h.lang)) for t in notify.channels(s, h))
    return {"queued": n}


@router.get("/api/v1/vapid-public-key")
def vapid_key():
    key = config.VAPID_PUBLIC_KEY
    if not key:
        raise Problem(503, "not_configured", "Web push isn't set up on this server")
    return {"key": key}


@router.post("/api/v1/notices/{notice_id}/opened", status_code=204)
def notice_opened(notice_id: Annotated[str, Path(pattern=UUID)]):
    with db.session() as s:
        n = s.get(NoticeLog, notice_id)
        if not n:
            raise Problem(404, "not_found", "Not found")
        if n.status == "sent" and not n.opened_at:
            n.opened_at, n.status = db.utcnow(), "opened"
    return Response(status_code=204)


# ------------------------------------------------------------------ internal (also block /internal/* at the proxy)
def job_secret(x_job_secret: Optional[str] = Header(None)):
    if not config.INTERNAL_JOB_SECRET:
        raise Problem(404, "not_found", "Not found")
    if not x_job_secret or not secure.same(x_job_secret, config.INTERNAL_JOB_SECRET):
        raise Problem(403, "forbidden", "Forbidden")


@internal.post("/internal/jobs/{name}", dependencies=[Depends(job_secret)])
def run_job(name: Annotated[str, Path(pattern=r"^[a-z_]{3,40}$")]):
    if name not in jobs.JOBS:
        raise Problem(404, "not_found", "Unknown job")
    return jobs.run(name)


@internal.get("/internal/metrics", dependencies=[Depends(job_secret)])
def metrics():
    from engine import weather
    day = db.utcnow() - timedelta(days=1)
    with db.session() as s:
        by_status = dict(s.execute(select(NoticeLog.status, func.count()).where(NoticeLog.queued_at >= day).group_by(NoticeLog.status)).all())
        otps = s.scalar(select(func.count()).select_from(Otp).where(Otp.created_at >= day)) or 0
        stops = s.scalar(select(func.count()).select_from(ConsentEvent).where(ConsentEvent.action == "withdrawn", ConsentEvent.at >= day)) or 0
        homes = s.scalar(select(func.count()).select_from(Household).where(Household.alerts_enabled.is_(True))) or 0
    return {"time": db.utcnow().isoformat(timespec="seconds"), "http": observe.snapshot(), "weather": weather.status(),
            "alerts_last_24h": by_status, "otp_last_24h": otps, "otp_daily_cap": config.OTP_DAILY_CAP, "stop_last_24h": stops,
            "alert_homes": homes, "alerts_enabled_global": config.ALERTS_ENABLED_GLOBAL}
