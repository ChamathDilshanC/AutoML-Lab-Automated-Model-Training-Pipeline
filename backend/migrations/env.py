"""Alembic environment.

The database URL comes from the application settings, so migrations always run against the same
database as the app. On PostgreSQL a session-level advisory lock serialises concurrent runs (for
example two API instances starting at once during a deployment): the second waits, then finds
the schema already current.
"""

from alembic import context
from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.session import Base, make_engine

config = context.config
target_metadata = Base.metadata

ADVISORY_LOCK_KEY = 727274  # arbitrary, but must be the same in every process


def _url() -> str:
    override = config.attributes.get("url")
    return str(override) if override else get_settings().effective_database_url


def _migrate(connection: Connection) -> None:
    postgres = connection.dialect.name == "postgresql"
    if postgres:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
        connection.commit()
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        if postgres:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
            connection.commit()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    try:
        with engine.connect() as connection:
            _migrate(connection)
    finally:
        engine.dispose()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
