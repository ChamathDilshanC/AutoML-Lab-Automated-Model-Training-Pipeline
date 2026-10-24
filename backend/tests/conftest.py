"""Shared fixtures: an app wired to an in-memory database and a temporary storage directory."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_session
from app.main import create_app
from app.services.storage import LocalStorage

UPLOAD_LIMIT = 20_000


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> Iterator[FastAPI]:
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(UPLOAD_LIMIT))
    get_settings.cache_clear()
    application = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    yield application
    get_settings.cache_clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """The same directory the app uses, for code that runs outside the web app (the worker)."""
    return LocalStorage(tmp_path / "storage")
