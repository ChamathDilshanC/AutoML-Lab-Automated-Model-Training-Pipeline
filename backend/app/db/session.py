from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings, normalize_database_url


class Base(DeclarativeBase):
    """Declarative base for metadata models."""


def make_engine(database_url: str) -> Engine:
    database_url = normalize_database_url(database_url)
    connect_args: dict[str, Any] = {}
    pool_options: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        # A small pool: the API and the worker each hold a few connections to a small database.
        # Pre-ping and recycling replace connections that the server or a network device dropped.
        pool_options = {
            "pool_size": 5,
            "max_overflow": 5,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
    engine = create_engine(database_url, connect_args=connect_args, **pool_options)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # The API and the worker are separate processes sharing one file: WAL lets readers
            # and a writer overlap, and the timeout waits for a lock instead of failing.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine = make_engine(get_settings().effective_database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_local_tables() -> None:
    """Create tables directly from the models, for `ENVIRONMENT=local` only.

    Anywhere else the schema comes from the Alembic migrations (`python -m app.migrate`).
    Creating tables outside them would make the first real migration fail with "table exists".
    """
    if get_settings().environment == "local":
        Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    with SessionLocal() as session:
        yield session
