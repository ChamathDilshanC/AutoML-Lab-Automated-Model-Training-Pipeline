"""The sign-in rate limit must see the real client behind a proxy, and must not be spoofable."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.client_ip import client_ip
from app.core.config import get_settings
from app.core.rate_limit import RateLimiter
from tests.conftest import TEST_PASSWORD, TestUser


def request(forwarded: str | None, peer: str | None = "10.0.0.5") -> Any:
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer) if peer else None)


def test_without_a_proxy_the_header_is_ignored() -> None:
    assert client_ip(request("1.2.3.4"), trusted_hops=0) == "10.0.0.5"


def test_with_one_proxy_the_last_entry_is_the_client() -> None:
    assert client_ip(request("203.0.113.9"), trusted_hops=1) == "203.0.113.9"


def test_entries_a_client_added_at_the_front_are_ignored() -> None:
    forged = "6.6.6.6, 7.7.7.7, 203.0.113.9"
    assert client_ip(request(forged), trusted_hops=1) == "203.0.113.9"


def test_with_two_proxies_the_second_from_the_right_is_the_client() -> None:
    assert client_ip(request("9.9.9.9, 203.0.113.9, 172.16.0.1"), trusted_hops=2) == "203.0.113.9"


@pytest.mark.parametrize("header", [None, "", " , ", "203.0.113.9"])
def test_a_missing_or_short_header_falls_back_to_the_connecting_address(
    header: str | None,
) -> None:
    # Two proxies are expected but at most one entry is present: the request did not come the
    # way we expect, so do not trust what it claims.
    assert client_ip(request(header), trusted_hops=2) == "10.0.0.5"


def test_no_client_at_all_is_handled() -> None:
    assert client_ip(request(None, peer=None), trusted_hops=1) == "unknown"


# --- the sign-in limiter, end to end -------------------------------------------------------------


@pytest.fixture
def behind_one_proxy(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    get_settings.cache_clear()
    app.state.login_limiter = RateLimiter(3, 60, clock=lambda: 0.0)


def attempt(client: TestClient, forwarded: str) -> int:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "alice", "password": "wrong"},
        headers={"X-Forwarded-For": forwarded},
    )
    return response.status_code


def test_one_client_cannot_dodge_the_limit_by_inventing_addresses(
    behind_one_proxy: None, anonymous_client: TestClient, alice: TestUser
) -> None:
    # The proxy appends the real address (203.0.113.9); the client invents the rest.
    codes = [attempt(anonymous_client, f"10.0.0.{n}, 203.0.113.9") for n in range(1, 6)]
    assert codes == [401, 401, 401, 429, 429]


def test_other_clients_are_not_blocked_by_someone_elses_failures(
    behind_one_proxy: None, anonymous_client: TestClient, alice: TestUser
) -> None:
    for _ in range(4):
        attempt(anonymous_client, "198.51.100.7, 203.0.113.9")
    # A different real client (a different last entry) still has its full allowance.
    other = anonymous_client.post(
        "/api/v1/auth/login",
        data={"username": "alice", "password": TEST_PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.77"},
    )
    assert other.status_code == 200


def test_without_trusted_proxies_the_header_changes_nothing(
    app: FastAPI, anonymous_client: TestClient, alice: TestUser
) -> None:
    app.state.login_limiter = RateLimiter(3, 60, clock=lambda: 0.0)
    codes = [attempt(anonymous_client, f"5.5.5.{n}") for n in range(1, 6)]
    assert codes == [401, 401, 401, 429, 429]  # every request counts against the one real peer
