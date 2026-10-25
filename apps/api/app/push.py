"""App and browser push (spec §4 Phase 4, §6.5): FCM HTTP v1 for the Android/iOS app, Web Push (RFC 8291 aes128gcm
+ RFC 8292 VAPID) for the website. Built on `cryptography` and httpx only.
- A browser's push endpoint comes from the user, so it must belong to a known push service (no SSRF, spec §8.1).
- Without credentials: a fake sender in dev (writes to the outbox), an error in prod.
- Push texts follow the same rule as SMS/WhatsApp: no health details (spec §2 rule 7)."""
import base64
import json
import os
import threading
import time
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config
from .messaging import FakeProvider, SendError

PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com", ".push.apple.com", ".notify.windows.com")
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
GOOGLE_OAUTH_ENDPOINT = "https://oauth2.googleapis.com/token"
TTL_S = 12 * 3600                 # an unread heat alert is still useful the same evening and night


class Gone(SendError):
    """The device or browser unsubscribed: deactivate the target."""


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def endpoint_ok(url: str) -> bool:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS)


# ------------------------------------------------------------------ Web Push encryption (RFC 8291) and VAPID (RFC 8292)
def _hmac(key: bytes, data: bytes) -> bytes:
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


def encrypt(plaintext: bytes, ua_public: bytes, auth_secret: bytes, as_private: ec.EllipticCurvePrivateKey | None = None,
            salt: bytes | None = None, rs: int = 4096) -> bytes:
    """One aes128gcm record (RFC 8291 §4, RFC 8188). as_private and salt are only passed in by the RFC test vector."""
    as_private = as_private or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    as_public = as_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = as_private.exchange(ec.ECDH(), ua_key)
    ikm = _hmac(_hmac(auth_secret, shared), b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    body = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + rs.to_bytes(4, "big") + bytes([len(as_public)]) + as_public + body


def vapid_header(endpoint: str, now: int | None = None) -> str:
    key = ec.derive_private_key(int.from_bytes(unb64u(config.VAPID_PRIVATE_KEY), "big"), ec.SECP256R1())
    u = urlparse(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": (now or int(time.time())) + TTL_S, "sub": config.VAPID_SUBJECT},
                             separators=(",", ":")).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    jwt = f"{head}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={config.VAPID_PUBLIC_KEY}"


# ------------------------------------------------------------------ senders
class PushSender:
    name = "base"

    def send(self, target, title: str, body: str, notice_id: str) -> str:
        raise NotImplementedError


class WebPush(PushSender):
    name = "webpush"

    def send(self, target, title, body, notice_id):
        if not endpoint_ok(target.endpoint or ""):
            raise Gone("endpoint is not a known push service")
        payload = json.dumps({"title": title, "body": body, "notice_id": notice_id}, ensure_ascii=False).encode()
        data = encrypt(payload, unb64u(target.p256dh), unb64u(target.auth))
        r = httpx.post(target.endpoint, content=data, timeout=5.0, headers={
            "Authorization": vapid_header(target.endpoint), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
            "TTL": str(TTL_S), "Urgency": "high"})
        if r.status_code in (404, 410):
            raise Gone(f"webpush {r.status_code}")
        if r.status_code >= 300:
            raise SendError(f"webpush {r.status_code}")
        return r.headers.get("location", "webpush")


class Fcm(PushSender):
    name = "fcm"
    _lock = threading.Lock()

    def __init__(self, credentials: dict):
        if credentials.get("token_uri", GOOGLE_OAUTH_ENDPOINT) != GOOGLE_OAUTH_ENDPOINT:
            raise SendError("unexpected token_uri in FCM credentials")
        self.cred = credentials
        self._token: tuple[str, float] | None = None

    def _access_token(self) -> str:
        with self._lock:
            if self._token and self._token[1] > time.time() + 60:
                return self._token[0]
            now = int(time.time())
            head = b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
            claims = b64u(json.dumps({"iss": self.cred["client_email"], "scope": FCM_SCOPE, "aud": GOOGLE_OAUTH_ENDPOINT, "iat": now, "exp": now + 3600}).encode())
            key = serialization.load_pem_private_key(self.cred["private_key"].encode(), password=None)
            if not isinstance(key, rsa.RSAPrivateKey):
                raise SendError("FCM credentials need an RSA private key")
            sig = key.sign(f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
            r = httpx.post(GOOGLE_OAUTH_ENDPOINT, timeout=5.0, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                                 "assertion": f"{head}.{claims}.{b64u(sig)}"})
            if r.status_code != 200:
                raise SendError(f"fcm auth {r.status_code}")
            d = r.json()
            self._token = (d["access_token"], time.time() + int(d.get("expires_in", 3600)))
            return self._token[0]

    def send(self, target, title, body, notice_id):
        url = f"https://fcm.googleapis.com/v1/projects/{self.cred['project_id']}/messages:send"
        msg = {"message": {"token": target.fcm_token, "notification": {"title": title, "body": body}, "data": {"notice_id": notice_id},
                           "android": {"priority": "high", "ttl": f"{TTL_S}s"}}}
        r = httpx.post(url, json=msg, timeout=5.0, headers={"Authorization": "Bearer " + self._access_token()})
        if r.status_code == 404 or "UNREGISTERED" in r.text:
            raise Gone("fcm token unregistered")
        if r.status_code >= 300:
            raise SendError(f"fcm {r.status_code}")
        return r.json().get("name", "fcm")


class FakePush(PushSender):
    """Dev and tests: writes title/body to the outbox, never the device token or endpoint."""
    name = "fake"

    def __init__(self):
        self.out = FakeProvider()
        self.sent: list[dict] = []

    def send(self, target, title, body, notice_id):
        self.sent.append({"kind": target.kind, "title": title, "body": body, "notice_id": notice_id})
        return self.out.send(target.kind, "-" * 10, "push", f"{title}: {body}")


_SENDERS: dict = {}


def sender(kind: str) -> PushSender:
    if kind in _SENDERS:
        return _SENDERS[kind]
    if kind == "fcm" and config.FCM_CREDENTIALS_JSON:
        raw = config.FCM_CREDENTIALS_JSON
        cred = json.load(open(raw, encoding="utf-8")) if os.path.exists(raw) else json.loads(raw)
        return _SENDERS.setdefault(kind, Fcm(cred))
    if kind == "webpush" and config.VAPID_PRIVATE_KEY and config.VAPID_PUBLIC_KEY and config.VAPID_SUBJECT:
        return _SENDERS.setdefault(kind, WebPush())
    if config.PROD:
        raise SendError(f"{kind} push isn't configured")
    return _SENDERS.setdefault(kind, FakePush())


def set_sender(kind: str, s: PushSender | None):
    _SENDERS.pop(kind, None)
    if s:
        _SENDERS[kind] = s
