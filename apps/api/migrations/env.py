"""Alembic environment: the URL comes from the caller (app.db.migrate) or DATABASE_URL; metadata from app.models."""
from alembic import context
from sqlalchemy import engine_from_config, pool

from app import config, models  # noqa: F401  (registers the tables)
from app.db import Base

cfg = context.config
url = cfg.get_main_option("sqlalchemy.url") or config.DATABASE_URL
target_metadata = Base.metadata


def run_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online():
    connectable = engine_from_config({"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # batch mode lets later migrations alter columns on SQLite too
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
