"""Migrations must build exactly the schema the models declare.

Runs on SQLite by default. Set TEST_DATABASE_URL to a PostgreSQL URL (CI does) to run the same
checks on the real database; its `public` schema is emptied before and after.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app import migrate
from app.db import models  # noqa: F401  (registers the tables)
from app.db.session import Base

POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _reset(url: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


@pytest.fixture
def url(tmp_path: Path) -> Iterator[str]:
    database = POSTGRES_URL or f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    _reset(database)
    yield database
    _reset(database)


def tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def schema_differences(url: str) -> list[Any]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "compare_server_default": False}
            )
            return list(compare_metadata(context, Base.metadata))
    finally:
        engine.dispose()


def test_upgrading_creates_every_table_the_models_declare(url: str) -> None:
    assert tables(url) == set()
    migrate.upgrade(url)
    assert tables(url) == set(Base.metadata.tables) | {"alembic_version"}
    assert migrate.current_revision(url) == migrate.head_revision()


def test_the_migrated_schema_matches_the_models_exactly(url: str) -> None:
    """Columns, types, nullability, indexes, unique constraints and foreign keys."""
    migrate.upgrade(url)
    assert schema_differences(url) == []


def test_upgrading_twice_is_harmless(url: str) -> None:
    migrate.upgrade(url)
    migrate.upgrade(url)
    assert migrate.current_revision(url) == migrate.head_revision()


def test_downgrading_removes_everything(url: str) -> None:
    migrate.upgrade(url)
    migrate.downgrade(url)
    assert tables(url) <= {"alembic_version"}
    migrate.upgrade(url)  # and it can be applied again afterwards
    assert schema_differences(url) == []


def test_an_unmigrated_database_is_detected(url: str) -> None:
    assert migrate.current_revision(url) is None
    with pytest.raises(TimeoutError):
        migrate.wait_until_migrated(url, timeout_seconds=0, poll_seconds=0, sleep=lambda _: None)


def test_waiting_returns_as_soon_as_the_schema_is_current(url: str) -> None:
    attempts = {"n": 0}

    def sleep(_: float) -> None:
        attempts["n"] += 1
        if attempts["n"] == 2:  # "the API finishes migrating" while the worker waits
            migrate.upgrade(url)

    migrate.wait_until_migrated(url, timeout_seconds=60, poll_seconds=0, sleep=sleep)
    assert attempts["n"] == 2


def test_waiting_survives_a_database_that_is_not_up_yet(tmp_path: Path) -> None:
    missing = f"sqlite:///{(tmp_path / 'no' / 'such' / 'dir' / 'x.db').as_posix()}"
    ticks = iter(range(100))
    with pytest.raises(TimeoutError):
        migrate.wait_until_migrated(
            missing,
            timeout_seconds=3,
            poll_seconds=0,
            sleep=lambda _: None,
            clock=lambda: float(next(ticks)),
        )


def test_there_is_exactly_one_migration_head() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrate.alembic_config())
    assert len(script.get_heads()) == 1


def test_processes_started_together_do_not_race(url: str) -> None:
    """Two API instances starting at once during a deployment must not both create the tables.

    Separate processes, as in production (Alembic keeps global state, so threads are not a
    valid way to test this). The PostgreSQL advisory lock makes the others wait.
    """
    if not POSTGRES_URL:
        pytest.skip("advisory locks are a PostgreSQL feature")
    env = {**os.environ, "DATABASE_URL": url, "ENVIRONMENT": "local"}
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "app.migrate"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for _ in range(4)
    ]
    outputs = [process.communicate(timeout=180)[0] for process in processes]
    assert [process.returncode for process in processes] == [0, 0, 0, 0], "\n".join(outputs)
    assert migrate.current_revision(url) == migrate.head_revision()
