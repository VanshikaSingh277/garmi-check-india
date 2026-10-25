"""Encrypted database backups (spec §8.11): SQLite online backup, AES-GCM with BACKUP_ENC_KEY, kept 14 days.
Copying the files to object storage is a deploy step (docs/DEPLOY.md, Phase 7). Postgres uses pg_dump instead."""
import base64
import glob
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config, db
from .secure import NotConfigured


def _key() -> bytes:
    if not config.BACKUP_ENC_KEY:
        raise NotConfigured("BACKUP_ENC_KEY")
    key = base64.b64decode(config.BACKUP_ENC_KEY)
    if len(key) != 32:
        raise NotConfigured("BACKUP_ENC_KEY is not 32 bytes")
    return key


def _sqlite_path() -> str:
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or not url.database:
        raise NotConfigured("backups here handle SQLite only; use pg_dump for Postgres")
    return url.database


def make(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy.db")
        src, dst = sqlite3.connect(_sqlite_path()), sqlite3.connect(copy)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(copy, "rb") as f:
            raw = f.read()
    nonce = os.urandom(12)
    path = os.path.join(config.BACKUP_DIR, f"thandak-{now:%Y%m%d-%H%M%S}.db.enc")
    with open(path, "wb") as f:
        f.write(nonce + AESGCM(_key()).encrypt(nonce, raw, b"thandak-backup"))
    removed = 0
    for old in glob.glob(os.path.join(config.BACKUP_DIR, "thandak-*.db.enc")):
        stamp = os.path.basename(old)[8:23]
        if datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc) < now - timedelta(days=config.BACKUP_KEEP_DAYS):
            os.remove(old)
            removed += 1
    return {"file": os.path.basename(path), "bytes": len(raw), "removed_old": removed}


def restore(path: str, target_db: str):
    """Decrypt a backup into a database file (never over the live one while the app runs)."""
    with open(path, "rb") as f:
        blob = f.read()
    raw = AESGCM(_key()).decrypt(blob[:12], blob[12:], b"thandak-backup")
    with open(target_db, "wb") as f:
        f.write(raw)


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["make"]:
        print(make())
    elif sys.argv[1:2] == ["restore"] and len(sys.argv) == 4:
        restore(sys.argv[2], sys.argv[3])
        print("restored to", sys.argv[3])
    else:
        print("usage: python -m app.backup make | restore <backup.db.enc> <new.db>")
