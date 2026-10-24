"""Shared fixtures: an app wired to an in-memory database and a temporary storage directory.

The default `client` is signed in as a real user with a real token, so ordinary tests exercise the
same authentication path as production. `anonymous_client` has no token.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.passwords import hash_password
from app.core.tokens import create_access_token, resolve_secret_key
from app.db import users as user_repo
from app.db.session import Base, get_session
from app.main import create_app
from app.services.storage import LocalStorage

UPLOAD_LIMIT = 20_000
TEST_SECRET = "test-secret-key-that-is-definitely-long-enough-0123456789"
TEST_PASSWORD = "correct horse battery staple"
_PASSWORD_HASH = hash_password(TEST_PASSWORD)  # hashing is slow on purpose; do it once


@dataclass(frozen=True)
class TestUser:
    __test__ = False  # not a pytest test class

    user_id: str
    username: str
    password: str
    headers: dict[str, str]


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
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    # Generous by default so ordinary tests never trip the limiters; the rate-limit tests set
    # their own.
    monkeypatch.setenv("PREDICT_RATE_LIMIT_PER_MINUTE", "100000")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_PER_MINUTE", "100000")
    get_settings.cache_clear()
    application = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    yield application
    get_settings.cache_clear()


@pytest.fixture
def make_user(app: FastAPI, session_factory: sessionmaker[Session]) -> Callable[..., TestUser]:
    def make(username: str = "alice") -> TestUser:
        with session_factory() as session:
            user = user_repo.create_user(session, username, _PASSWORD_HASH)
        token, _ = create_access_token(user.user_id, resolve_secret_key(get_settings()), 60)
        return TestUser(
            user.user_id, user.username, TEST_PASSWORD, {"Authorization": f"Bearer {token}"}
        )

    return make


@pytest.fixture
def alice(make_user: Callable[..., TestUser]) -> TestUser:
    return make_user("alice")


@pytest.fixture
def client(app: FastAPI, alice: TestUser) -> TestClient:
    """Signed in as alice."""
    return TestClient(app, raise_server_exceptions=False, headers=alice.headers)


@pytest.fixture
def anonymous_client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_for(app: FastAPI) -> Callable[[TestUser], TestClient]:
    def build(user: TestUser) -> TestClient:
        return TestClient(app, raise_server_exceptions=False, headers=user.headers)

    return build


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """The same directory the app uses, for code that runs outside the web app (the worker)."""
    return LocalStorage(tmp_path / "storage")
