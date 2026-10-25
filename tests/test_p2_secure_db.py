"""Database, migrations, phone protection and backups (spec §4, §5, §8.2-8.3, §8.11, §10.3, §10.4)."""
import hashlib
import os
import sqlite3
import tempfile

from alembic import command
from alembic.config import Config

from app import backup, config, db, secure
from p2_helpers import home

API = os.path.join(os.path.dirname(__file__), "..", "apps", "api")


def test_migrations_upgrade_downgrade_upgrade():
    with tempfile.TemporaryDirectory() as d:
        url = "sqlite:///" + os.path.join(d, "m.db").replace("\\", "/")
        cfg = Config(os.path.join(API, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(API, "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        con = sqlite3.connect(url[len("sqlite:///"):])
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        con.close()
        assert {"household", "push_target", "otp", "notice_log", "consent_event", "job_lock", "imd_warning", "daily_aggregate"} <= tables
        assert {"org", "worker", "worker_session", "access_log", "person"} <= tables

        def tables_now():
            con = sqlite3.connect(url[len("sqlite:///"):])
            try:
                return {r[0] for r in con.execute("select name from sqlite_master where type='table'")} - {"alembic_version"}
            finally:
                con.close()
        assert {"reading", "feedback", "fix_progress"} <= tables
        command.downgrade(cfg, "-1")                                      # one step: only the newest migration's tables go
        assert "household" in tables_now() and "worker" in tables_now() and "reading" not in tables_now()
        command.downgrade(cfg, "base")
        assert not tables_now(), tables_now()
        command.upgrade(cfg, "head")


def test_phone_hmac_is_keyed_not_a_plain_hash():
    p = "+919812345678"
    assert secure.phone_hmac(p) != hashlib.sha256(p.encode()).hexdigest()
    assert secure.phone_hmac(p) == secure.phone_hmac(p)


def test_phone_encryption_round_trip_and_key_rotation():
    p = "+919812345678"
    blob, kid = secure.encrypt_phone(p)
    assert p.encode() not in blob and secure.decrypt_phone(blob, kid) == p
    old = config.PHONE_ENC_KEYS
    try:
        config.PHONE_ENC_KEYS = "k2:" + __import__("base64").b64encode(b"\x03" * 32).decode() + "," + old
        new_blob, new_kid = secure.encrypt_phone(p)
        assert new_kid == "k2" and secure.decrypt_phone(new_blob, new_kid) == p
        assert secure.decrypt_phone(blob, kid) == p          # rows under the old key still read
    finally:
        config.PHONE_ENC_KEYS = old


def test_only_indian_mobiles():
    assert secure.normalise_phone("98123 45678") == "+919812345678"
    assert secure.normalise_phone("+91-98123-45678") == "+919812345678"
    for bad in ("+14155550100", "1234567890", "98123", "+91 5812345678", ""):
        assert secure.normalise_phone(bad) is None, bad


def test_tokens_are_stored_as_hashes():
    hid, token = home(phone=None)
    con = sqlite3.connect(db.engine.url.database)
    stored = [r[0] for r in con.execute("select token_hash from household where id=?", (hid,))]
    dump = "\n".join(con.iterdump())
    con.close()
    assert stored == [secure.token_hash(token)] and token not in dump


def test_backup_and_restore():
    hid, _ = home(phone=None)
    out = backup.make()
    path = os.path.join(config.BACKUP_DIR, out["file"])
    with open(path, "rb") as f:
        assert b"household" not in f.read()                  # encrypted
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "restored.db")
        backup.restore(path, target)
        con = sqlite3.connect(target)
        assert con.execute("select count(*) from household where id=?", (hid,)).fetchone()[0] == 1
        con.close()
