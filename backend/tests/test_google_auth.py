from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import User

SUPABASE_SECRET = "supabase-test-secret-that-is-long-enough-0123456789"
SUPABASE_URL = "https://example.supabase.co"


def supabase_token(subject: str = "google-subject", **claims: Any) -> str:
    payload: dict[str, Any] = {
        "sub": subject,
        "email": "person@example.com",
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    payload.update(claims)
    return jwt.encode(payload, SUPABASE_SECRET, algorithm="HS256")


@pytest.fixture
def app_env() -> dict[str, str]:
    return {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_JWT_SECRET": SUPABASE_SECRET}


def test_google_sign_in_creates_and_reuses_local_user(
    anonymous_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = anonymous_client.post("/api/v1/auth/google", json={"access_token": supabase_token()})
    assert response.status_code == 200
    token = response.json()["access_token"]
    second = anonymous_client.post("/api/v1/auth/google", json={"access_token": supabase_token()})
    assert second.status_code == 200
    with session_factory() as session:
        users = list(session.query(User).where(User.auth_subject == "google-subject"))
        assert len(users) == 1
        assert users[0].email == "person@example.com"
    me = anonymous_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "person@example.com"


def test_google_sign_in_rejects_wrong_audience(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        "/api/v1/auth/google",
        json={"access_token": supabase_token(aud="other")},
    )
    assert response.status_code == 401
