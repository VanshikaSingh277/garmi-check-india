"""Tokens, phone numbers and codes (spec §8.2-8.3).
- Tokens: 32 random bytes; only SHA-256(token + pepper) is stored; compared in constant time.
- Phones: AES-GCM with a random nonce and a key id (PHONE_ENC_KEYS key ring, first key encrypts); lookups use
  HMAC-SHA256(phone, PHONE_HMAC_KEY) - never a plain hash, 10-digit numbers are easy to brute-force.
- Indian mobiles only (+91, 10 digits starting 6-9)."""
import base64
import hashlib
import hmac
import os
import re
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config

MOBILE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")


class NotConfigured(Exception):
    """A secret this feature needs isn't set in the environment."""


def _need(*names: str):
    gone = config.missing(*names)
    if gone:
        raise NotConfigured(", ".join(gone))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    _need("TOKEN_PEPPER")
    return hashlib.sha256((token + config.TOKEN_PEPPER).encode()).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def normalise_phone(raw: str) -> str | None:
    """'+91 98xxxxxxxx', '098xxxxxxxx', '98xxxxxxxx' -> '+9198xxxxxxxx'; anything else -> None."""
    m = MOBILE.match(re.sub(r"[\s\-()]", "", raw or ""))
    return "+91" + m.group(1) if m else None


def phone_hmac(phone: str) -> str:
    _need("PHONE_HMAC_KEY")
    return hmac.new(config.PHONE_HMAC_KEY.encode(), phone.encode(), hashlib.sha256).hexdigest()


def _keys(ring: str = "PHONE_ENC_KEYS") -> list[tuple[str, bytes]]:
    _need(ring)
    out = []
    for part in getattr(config, ring).split(","):
        kid, _, b64 = part.strip().partition(":")
        key = base64.b64decode(b64)
        if len(key) != 32:
            raise NotConfigured(f"{ring} key {kid!r} is not 32 bytes")
        out.append((kid, key))
    return out


def encrypt_phone(phone: str) -> tuple[bytes, str]:
    kid, key = _keys()[0]
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, phone.encode(), kid.encode()), kid


def decrypt_phone(blob: bytes, kid: str) -> str:
    """Only send_queue and webhook replies call this (spec §8.3)."""
    key = dict(_keys())[kid]
    return AESGCM(key).decrypt(blob[:12], blob[12:], kid.encode()).decode()


def encrypt_field(value: str, ring: str = "PERSON_ENC_KEYS") -> tuple[bytes, str]:
    """Worker-managed person fields (spec §5.3): their own key ring, so a phone-key leak doesn't open them."""
    kid, key = _keys(ring)[0]
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, value.encode(), (ring + ":" + kid).encode()), kid


def decrypt_field(blob: bytes, kid: str, ring: str = "PERSON_ENC_KEYS") -> str:
    key = dict(_keys(ring))[kid]
    return AESGCM(key).decrypt(blob[:12], blob[12:], (ring + ":" + kid).encode()).decode()


def code_hash(code: str, phone_h: str) -> str:
    _need("TOKEN_PEPPER")
    return hmac.new(config.TOKEN_PEPPER.encode(), f"{phone_h}:{code}".encode(), hashlib.sha256).hexdigest()


def ip_hash(ip: str) -> str:
    key = (config.LOG_HASH_SECRET or config.TOKEN_PEPPER or "thandak").encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


REQUIRED_IN_PROD = ("TOKEN_PEPPER", "PHONE_HMAC_KEY", "PHONE_ENC_KEYS", "PERSON_ENC_KEYS", "LOG_HASH_SECRET",
                    "INTERNAL_JOB_SECRET", "BACKUP_ENC_KEY")
PLAIN_SECRETS = ("TOKEN_PEPPER", "PHONE_HMAC_KEY", "LOG_HASH_SECRET", "INTERNAL_JOB_SECRET", "WHATSAPP_WEBHOOK_SECRET",
                 "SMS_WEBHOOK_SECRET")


def prod_problems() -> list[str]:
    """What stops a production start: missing, short, reused or malformed secrets, or no ALLOWED_HOSTS.
    Names only, never values."""
    out = [f"{n} is not set" for n in config.missing(*REQUIRED_IN_PROD)]
    out += [f"{n} is shorter than 32 characters" for n in PLAIN_SECRETS if getattr(config, n) and len(getattr(config, n)) < 32]
    for ring in ("PHONE_ENC_KEYS", "PERSON_ENC_KEYS"):
        if getattr(config, ring):
            try:
                _keys(ring)
            except (NotConfigured, ValueError) as e:
                out.append(f"{ring} is malformed ({type(e).__name__})")
    if config.BACKUP_ENC_KEY:
        try:
            if len(base64.b64decode(config.BACKUP_ENC_KEY, validate=True)) != 32:
                out.append("BACKUP_ENC_KEY is not 32 bytes")
        except ValueError:
            out.append("BACKUP_ENC_KEY is not base64")
    values: dict[str, str] = {}
    for n in PLAIN_SECRETS + ("BACKUP_ENC_KEY",):
        if getattr(config, n):
            values[n] = getattr(config, n)
    for ring in ("PHONE_ENC_KEYS", "PERSON_ENC_KEYS"):
        for i, part in enumerate(p for p in getattr(config, ring).split(",") if p.strip()):
            values[f"{ring}[{i}]"] = part.strip().partition(":")[2]
    seen: dict[str, str] = {}
    for n, v in values.items():
        if v in seen:
            out.append(f"{n} reuses the value of {seen[v]}")
        seen.setdefault(v, n)
    if not config.ALLOWED_HOSTS:
        out.append("ALLOWED_HOSTS is not set")
    return out
