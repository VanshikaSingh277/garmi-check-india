"""Database (spec §4): SQLite in WAL mode now, Postgres later, through SQLAlchemy 2 and Alembic. Portable types only;
UUIDs as text; times stored as naive UTC. The file lives on the writable state volume, never in data/."""
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


def _make_engine(url: str):
    if url.startswith("sqlite:///"):
        os.makedirs(os.path.dirname(url[len("sqlite:///"):]) or ".", exist_ok=True)
    eng = create_engine(url, future=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(conn, _rec):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()
    return eng


URL = config.DATABASE_URL
engine = _make_engine(URL)
Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def use(url: str):
    """Point the app at another database (tests, restore checks)."""
    global engine, URL
    URL, engine = url, _make_engine(url)
    Session.configure(bind=engine)


@contextmanager
def session():
    s = Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def migrate(url: str | None = None):
    """alembic upgrade head (run at startup by the web and jobs processes; safe to repeat)."""
    from alembic import command
    from alembic.config import Config
    here = os.path.join(os.path.dirname(__file__), "..")
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    cfg.set_main_option("sqlalchemy.url", (url or URL).replace("%", "%%"))   # configparser treats % as special
    command.upgrade(cfg, "head")


def ok() -> bool:
    try:
        with engine.connect() as c:
            c.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False
