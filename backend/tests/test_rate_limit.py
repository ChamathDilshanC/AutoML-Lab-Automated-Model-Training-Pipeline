"""Rate limiting: the limiter itself, and its use on the prediction endpoint."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.rate_limit import RateLimiter
from app.services.models import clear_model_cache
from app.services.storage import LocalStorage
from tests.conftest import TestUser
from tests.data import classification_csv, trained_model_id

INSTANCE = {"x1": 1.0, "x2": 0.0, "color": "red"}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# --- the limiter --------------------------------------------------------------------------------


def test_a_burst_up_to_the_limit_is_allowed_then_blocked() -> None:
    limiter = RateLimiter(3, 60, clock=Clock())
    assert [limiter.check("k")[0] for _ in range(5)] == [True, True, True, False, False]


def test_retry_after_says_when_the_next_request_will_pass() -> None:
    clock = Clock()
    limiter = RateLimiter(2, 60, clock=clock)  # one token every 30 seconds
    limiter.check("k")
    limiter.check("k")
    allowed, retry_after = limiter.check("k")
    assert (allowed, retry_after) == (False, 30)
    clock.now += 29
    assert limiter.check("k")[0] is False
    clock.now += 1
    assert limiter.check("k")[0] is True


def test_tokens_refill_gradually_and_never_beyond_the_limit() -> None:
    clock = Clock()
    limiter = RateLimiter(4, 60, clock=clock)
    for _ in range(4):
        limiter.check("k")
    clock.now += 15  # exactly one token back
    assert [limiter.check("k")[0] for _ in range(2)] == [True, False]
    clock.now += 10_000  # a long idle period does not bank extra tokens
    assert [limiter.check("k")[0] for _ in range(6)] == [True] * 4 + [False] * 2


def test_keys_are_independent() -> None:
    limiter = RateLimiter(1, 60, clock=Clock())
    assert limiter.check("alice")[0] is True
    assert limiter.check("alice")[0] is False
    assert limiter.check("bob")[0] is True


def test_memory_stays_bounded_with_many_keys() -> None:
    clock = Clock()
    limiter = RateLimiter(5, 60, clock=clock, max_keys=100)
    for i in range(1000):
        clock.now += 0.01
        limiter.check(f"key-{i}")
    assert len(limiter._buckets) <= 100


# --- on the prediction endpoint -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    clear_model_cache()


@pytest.fixture
def model_id(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> str:
    model = trained_model_id(
        client,
        session_factory,
        storage,
        classification_csv(),
        algorithms=["logistic_regression", "decision_tree"],
    )
    client.post(f"/api/v1/models/{model}/approve", json={"confirm": True})
    return model


def predict(client: TestClient, model_id: str, body: object | None = None):
    return client.post(f"/api/v1/models/{model_id}/predict", json=body or {"instances": [INSTANCE]})


def test_excess_predictions_get_429_with_retry_after(
    app: FastAPI, client: TestClient, model_id: str
) -> None:
    clock = Clock()
    app.state.predict_limiter = RateLimiter(3, 60, clock=clock)
    assert [predict(client, model_id).status_code for _ in range(3)] == [200, 200, 200]

    blocked = predict(client, model_id)
    assert blocked.status_code == 429
    error = blocked.json()["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["request_id"] == blocked.headers["X-Request-ID"]
    assert int(blocked.headers["Retry-After"]) == 20
    assert "predictions" not in blocked.text

    clock.now += 20
    assert predict(client, model_id).status_code == 200


def test_the_limit_applies_per_user(
    app: FastAPI,
    client: TestClient,
    client_for: Callable[[TestUser], TestClient],
    make_user: Callable[..., TestUser],
    model_id: str,
) -> None:
    app.state.predict_limiter = RateLimiter(2, 60, clock=Clock())
    bob = client_for(make_user("bob"))
    for _ in range(2):
        predict(client, model_id)
    assert predict(client, model_id).status_code == 429
    # Bob has his own allowance: he is not blocked, he simply does not own the model.
    assert predict(bob, model_id).status_code == 404


def test_malformed_requests_use_up_the_allowance(
    app: FastAPI, client: TestClient, model_id: str
) -> None:
    app.state.predict_limiter = RateLimiter(3, 60, clock=Clock())
    for _ in range(3):
        assert predict(client, model_id, {"instances": "not a list"}).status_code == 422
    assert predict(client, model_id).status_code == 429


def test_requests_for_unapproved_or_unknown_models_are_limited_too(
    app: FastAPI, client: TestClient
) -> None:
    app.state.predict_limiter = RateLimiter(2, 60, clock=Clock())
    assert predict(client, "md_unknown").status_code == 404
    assert predict(client, "md_unknown").status_code == 404
    assert predict(client, "md_unknown").status_code == 429


def test_other_endpoints_are_not_affected_by_the_prediction_limit(
    app: FastAPI, client: TestClient, model_id: str
) -> None:
    app.state.predict_limiter = RateLimiter(1, 60, clock=Clock())
    predict(client, model_id)
    assert predict(client, model_id).status_code == 429
    assert all(client.get("/api/v1/models").status_code == 200 for _ in range(20))


def test_unauthenticated_requests_are_refused_before_they_use_the_allowance(
    app: FastAPI, anonymous_client: TestClient, client: TestClient, model_id: str
) -> None:
    app.state.predict_limiter = RateLimiter(1, 60, clock=Clock())
    for _ in range(5):
        assert (
            anonymous_client.post(
                f"/api/v1/models/{model_id}/predict", json={"instances": [INSTANCE]}
            ).status_code
            == 401
        )
    assert predict(client, model_id).status_code == 200
