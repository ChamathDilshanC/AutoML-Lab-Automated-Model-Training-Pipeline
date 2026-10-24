"""Authentication: sign-in, token validation, protected routes, and secure defaults."""

import io
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import cli
from app.core import tokens
from app.core.config import Settings, get_settings
from app.core.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.core.rate_limit import RateLimiter
from app.core.tokens import TokenError, create_access_token, decode_access_token
from app.db.models import AuditEvent, Dataset, User
from app.main import create_app
from tests.conftest import TEST_PASSWORD, TEST_SECRET, TestUser

LOGIN = "/api/v1/auth/login"


def sign_in(client: TestClient, username: str, password: str):
    return client.post(LOGIN, data={"username": username, "password": password})


def token_for(user_id: str, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": user_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, TEST_SECRET, "HS256")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- signing in ---------------------------------------------------------------------------------


def test_signing_in_returns_a_token_that_works(
    anonymous_client: TestClient, alice: TestUser
) -> None:
    response = sign_in(anonymous_client, "alice", TEST_PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    headers = bearer(body["access_token"])
    assert anonymous_client.get("/api/v1/models", headers=headers).status_code == 200
    me = anonymous_client.get("/api/v1/auth/me", headers=headers).json()
    assert me == {"user_id": alice.user_id, "username": "alice"}


def test_usernames_are_case_insensitive(anonymous_client: TestClient, alice: TestUser) -> None:
    assert sign_in(anonymous_client, "ALICE", TEST_PASSWORD).status_code == 200


def test_wrong_password_and_unknown_user_look_identical(
    anonymous_client: TestClient, alice: TestUser
) -> None:
    wrong = sign_in(anonymous_client, "alice", "not the password")
    unknown = sign_in(anonymous_client, "nobody", "not the password")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.headers["WWW-Authenticate"] == unknown.headers["WWW-Authenticate"] == "Bearer"

    def shape(response: Any) -> dict[str, Any]:
        error = response.json()["error"]
        return {k: v for k, v in error.items() if k != "request_id"}

    assert shape(wrong) == shape(unknown)
    assert shape(wrong)["code"] == "UNAUTHENTICATED"
    assert "access_token" not in wrong.text


def test_a_disabled_user_cannot_sign_in_and_loses_existing_tokens(
    anonymous_client: TestClient, alice: TestUser, session_factory: sessionmaker[Session]
) -> None:
    assert anonymous_client.get("/api/v1/models", headers=alice.headers).status_code == 200
    with session_factory() as session:
        user = session.get(User, alice.user_id)
        assert user is not None
        user.is_active = False
        session.commit()
    assert sign_in(anonymous_client, "alice", TEST_PASSWORD).status_code == 401
    assert anonymous_client.get("/api/v1/models", headers=alice.headers).status_code == 401


def test_a_deleted_users_token_stops_working(
    anonymous_client: TestClient, alice: TestUser, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.delete(session.get(User, alice.user_id))
        session.commit()
    assert anonymous_client.get("/api/v1/models", headers=alice.headers).status_code == 401


def test_sign_in_attempts_are_audited_without_secrets(
    anonymous_client: TestClient, alice: TestUser, session_factory: sessionmaker[Session]
) -> None:
    sign_in(anonymous_client, "alice", TEST_PASSWORD)
    sign_in(anonymous_client, "Mallory", "hunter2hunter2hunter2")
    with session_factory() as session:
        events = list(session.scalars(select(AuditEvent).where(AuditEvent.action == "auth.login")))
    outcomes = sorted((e.outcome, e.actor_id is not None) for e in events)
    assert outcomes == [("failure", False), ("success", True)]
    dump = " ".join(str((e.detail, e.actor_id, e.resource_id)) for e in events)
    assert "mallory" in dump and "hunter2" not in dump and TEST_PASSWORD not in dump


def test_sign_in_is_rate_limited(
    app: FastAPI, anonymous_client: TestClient, alice: TestUser
) -> None:
    now = [0.0]
    app.state.login_limiter = RateLimiter(3, 60, clock=lambda: now[0])
    for _ in range(3):
        assert sign_in(anonymous_client, "alice", "wrong").status_code == 401
    blocked = sign_in(anonymous_client, "alice", TEST_PASSWORD)  # even the right password
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert "access_token" not in blocked.text
    now[0] += 60
    assert sign_in(anonymous_client, "alice", TEST_PASSWORD).status_code == 200


# --- token validation ---------------------------------------------------------------------------


def test_missing_token_is_401_with_the_error_envelope(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/api/v1/models")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    error = response.json()["error"]
    assert error["code"] == "UNAUTHENTICATED"
    assert error["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("header", ["Bearer garbage", "Bearer ", "Basic YWxpY2U6cHc=", "alice"])
def test_malformed_authorization_headers_are_rejected(
    anonymous_client: TestClient, header: str
) -> None:
    response = anonymous_client.get("/api/v1/models", headers={"Authorization": header})
    assert response.status_code == 401


def test_forged_and_invalid_tokens_are_rejected(
    anonymous_client: TestClient, alice: TestUser
) -> None:
    good_exp = datetime.now(UTC) + timedelta(minutes=10)
    forged = {
        "expired": token_for(alice.user_id, exp=datetime.now(UTC) - timedelta(seconds=5)),
        "wrong key": jwt.encode(
            {"sub": alice.user_id, "iat": datetime.now(UTC), "exp": good_exp},
            "another-key-another-key-another-key-0000",
            "HS256",
        ),
        "alg none": jwt.encode(
            {"sub": alice.user_id, "iat": datetime.now(UTC), "exp": good_exp}, None, "none"
        ),
        "other algorithm": jwt.encode(
            {"sub": alice.user_id, "iat": datetime.now(UTC), "exp": good_exp}, TEST_SECRET, "HS384"
        ),
        "no expiry": token_for(alice.user_id, exp=None),
        "no subject": token_for(None),
        "unknown subject": token_for("us_does_not_exist"),
        "tampered": token_for(alice.user_id)[:-4] + "AAAA",
    }
    for name, token in forged.items():
        response = anonymous_client.get("/api/v1/models", headers=bearer(token))
        assert response.status_code == 401, name


def test_every_api_route_except_sign_in_requires_a_token(
    app: FastAPI, anonymous_client: TestClient
) -> None:
    # The OpenAPI document lists every route, whatever FastAPI does internally with routers.
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/v1") or path == LOGIN:
            continue
        concrete = re.sub(r"\{[^}]+\}", "x", path)
        for method in operations:
            response = anonymous_client.request(method.upper(), concrete)
            assert response.status_code == 401, f"{method.upper()} {path} is not protected"
            checked += 1
    assert checked >= 14  # guards against the loop silently checking nothing


def test_health_check_stays_public(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/health").status_code == 200


def test_api_responses_carry_security_headers(
    client: TestClient, anonymous_client: TestClient
) -> None:
    api = client.get("/api/v1/models")
    assert api.headers["Cache-Control"] == "no-store"
    assert api.headers["X-Content-Type-Options"] == "nosniff"
    assert api.headers["Referrer-Policy"] == "no-referrer"
    health = anonymous_client.get("/health")
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert "no-store" not in health.headers.get("Cache-Control", "")
    assert anonymous_client.get("/api/v1/models").headers["Cache-Control"] == "no-store"


def test_cors_allows_the_authorization_header_and_delete(client: TestClient) -> None:
    response = client.options(
        "/api/v1/datasets/x",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize(
    ("method", "path", "headers"),
    [
        ("PUT", "/api/v1/datasets/ds_x/content", "authorization,content-type"),
        ("POST", "/api/v1/datasets", "authorization,content-type"),
        ("POST", "/api/v1/experiments", "authorization,content-type,idempotency-key"),
        ("DELETE", "/api/v1/datasets/ds_x", "authorization"),
    ],
)
def test_browser_preflights_pass_for_every_call_the_frontend_makes(
    client: TestClient, method: str, path: str, headers: str
) -> None:
    """A browser blocks a call unless the preflight allows its method and every header it sends.
    TestClient never preflights, so this is the only thing that catches a missing entry."""
    response = client.options(
        path,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )
    assert response.status_code == 200, f"{method} {path}: {response.text}"
    assert method in response.headers["access-control-allow-methods"]


# --- token and secret handling ------------------------------------------------------------------


def test_token_round_trip_and_expiry() -> None:
    token, lifetime = create_access_token("us_1", TEST_SECRET, 5)
    assert lifetime == 300
    assert decode_access_token(token, TEST_SECRET) == "us_1"
    old, _ = create_access_token("us_1", TEST_SECRET, 5, now=datetime.now(UTC) - timedelta(hours=1))
    with pytest.raises(TokenError):
        decode_access_token(old, TEST_SECRET)
    with pytest.raises(TokenError):
        decode_access_token(token, "a-different-secret-a-different-secret-1234")


def test_the_secret_key_is_required_outside_the_local_environment() -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
        tokens.resolve_secret_key(Settings(secret_key=None, environment="production"))
    with pytest.raises(RuntimeError, match="at least"):
        tokens.resolve_secret_key(Settings(secret_key="short", environment="production"))
    assert (
        tokens.resolve_secret_key(Settings(secret_key=TEST_SECRET, environment="production"))
        == TEST_SECRET
    )


def test_the_local_environment_gets_a_stable_temporary_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tokens, "_ephemeral_secret", None)
    first = tokens.resolve_secret_key(Settings(secret_key=None, environment="local"))
    assert len(first) >= tokens.MIN_SECRET_LENGTH
    assert tokens.resolve_secret_key(Settings(secret_key=None, environment="local")) == first


def test_the_app_refuses_to_start_in_production_without_a_secret(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SECRET_KEY")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


# --- passwords ----------------------------------------------------------------------------------


def test_password_hashes_are_salted_and_verify() -> None:
    first, second = hash_password("a long enough password"), hash_password("a long enough password")
    assert first != second  # random salt
    assert first.startswith("scrypt$") and "a long enough password" not in first
    assert verify_password("a long enough password", first)
    assert not verify_password("a long enough passworD", first)


@pytest.mark.parametrize(
    "stored", ["", "plain", "scrypt$1$2", "bcrypt$a$b$c$d$e", "scrypt$x$y$z$!!$!!"]
)
def test_a_malformed_stored_hash_never_matches(stored: str) -> None:
    assert verify_password("anything", stored) is False


def test_password_length_rules() -> None:
    validate_password_strength("x" * MIN_PASSWORD_LENGTH)
    validate_password_strength("x" * MAX_PASSWORD_LENGTH)
    for bad in ("x" * (MIN_PASSWORD_LENGTH - 1), "x" * (MAX_PASSWORD_LENGTH + 1)):
        with pytest.raises(ValueError):
            validate_password_strength(bad)


# --- the operator CLI ---------------------------------------------------------------------------


@pytest.fixture
def cli_db(monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]) -> None:
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "engine", session_factory.kw["bind"])


def test_cli_creates_a_user_who_can_sign_in(
    cli_db: None,
    anonymous_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("a perfectly long password\n"))
    assert cli.main(["create-user", "Bob", "--password-stdin"]) == 0
    assert "bob" in capsys.readouterr().out
    assert sign_in(anonymous_client, "bob", "a perfectly long password").status_code == 200


def test_cli_rejects_bad_input_with_safe_messages(cli_db: None, alice: TestUser) -> None:
    with pytest.raises(ValueError, match="already taken"):
        cli.create_user("ALICE", "a perfectly long password")
    with pytest.raises(ValueError, match="at least"):
        cli.create_user("carol", "short")
    for name in ("ab", "has space", "semi;colon", "x" * 65):
        with pytest.raises(ValueError, match="Username"):
            cli.create_user(name, "a perfectly long password")


def test_cli_claims_data_created_before_accounts_existed(
    cli_db: None, alice: TestUser, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(
            Dataset(
                dataset_id="ds_old",
                owner_id="local-user",
                storage_key="datasets/local-user/ds_old/source.csv",
                original_filename="old.csv",
                size_bytes=1,
                status="READY",
            )
        )
        session.commit()
    assert cli.claim_legacy("alice") == {"datasets": 1, "experiments": 0, "models": 0}
    with session_factory() as session:
        dataset = session.get(Dataset, "ds_old")
        assert dataset is not None and dataset.owner_id == alice.user_id
    with pytest.raises(ValueError, match="No such user"):
        cli.claim_legacy("nobody")


def test_the_cli_hashes_passwords_and_never_stores_them(
    cli_db: None, session_factory: sessionmaker[Session]
) -> None:
    cli.create_user("dave", "a perfectly long password")
    with session_factory() as session:
        user = session.scalar(select(User).where(User.username == "dave"))
        assert user is not None
        assert "perfectly" not in user.password_hash and user.password_hash.startswith("scrypt$")
