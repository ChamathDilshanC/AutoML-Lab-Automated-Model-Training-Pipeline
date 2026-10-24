"""Running database migrations: `python -m app.migrate`.

The API container runs this before it starts serving, and the worker waits for it
(`wait_until_migrated`). Locally (`ENVIRONMENT=local`) tables are still created on start-up for
convenience; everywhere else the schema comes only from the migrations in `migrations/`.
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app.core.config import get_settings, normalize_database_url

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(url: str | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if url:
        config.attributes["url"] = normalize_database_url(url)
    return config


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def current_revision(url: str | None = None) -> str | None:
    engine = create_engine(normalize_database_url(url or get_settings().effective_database_url))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def wait_until_migrated(
    url: str | None = None,
    *,
    timeout_seconds: float = 300.0,
    poll_seconds: float = 5.0,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Block until the database is at the latest migration, or raise `TimeoutError`.

    A worker that starts before the API has finished migrating would otherwise fail on missing
    tables; waiting here lets the container orchestrator start both at once.
    """
    deadline = clock() + timeout_seconds
    target = head_revision()
    while True:
        try:
            if current_revision(url) == target:
                return
        except Exception as exc:  # the database may still be starting
            logger.info("Database not ready yet: %s", type(exc).__name__)
        if clock() >= deadline:
            raise TimeoutError("The database schema is not at the latest migration.")
        sleep(poll_seconds)


def main() -> int:
    logging.basicConfig(level=get_settings().log_level)
    upgrade()
    print(f"Database is at revision {current_revision()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
