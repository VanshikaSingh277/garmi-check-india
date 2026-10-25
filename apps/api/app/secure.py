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
