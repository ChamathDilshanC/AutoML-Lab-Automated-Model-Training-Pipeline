"""IDOR protection: one user can never read, change or delete another user's resources.

A foreign ID must be indistinguishable from an ID that does not exist (404, same body), so the API
cannot be used to find out which IDs are real.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.services.models import clear_model_cache
from app.services.storage import LocalStorage
from tests.conftest import TestUser
from tests.data import (
    classification_csv,
    classification_payload,
    ready_dataset,
    trained_model_id,
)

INSTANCE = {"x1": 1.0, "x2": 0.0, "color": "red"}


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    clear_model_cache()


class World:
    """Alice owns a dataset, an experiment and an approved model. Bob owns nothing yet."""

    def __init__(self, alice: TestClient, bob: TestClient, ids: dict[str, str]) -> None:
        self.alice, self.bob, self.ids = alice, bob, ids


@pytest.fixture
def world(
    client: TestClient,
    client_for: Callable[[TestUser], TestClient],
    make_user: Callable[..., TestUser],
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
) -> World:
    dataset_id = ready_dataset(client, classification_csv())
    model_id = trained_model_id(
        client,
        session_factory,
        storage,
        b"",
        dataset_id=dataset_id,
        algorithms=["logistic_regression", "decision_tree"],
    )
    experiment_id = client.get(f"/api/v1/models/{model_id}").json()["experiment_id"]
    assert (
        client.post(f"/api/v1/models/{model_id}/approve", json={"confirm": True}).status_code == 200
    )
    bob = make_user("bob")
    return World(
        client,
        client_for(bob),
        {"dataset": dataset_id, "experiment": experiment_id, "model": model_id},
    )


def attempts(ids: dict[str, str]) -> list[tuple[str, str, dict[str, Any]]]:
    """Every way to touch a resource by ID, as (method, path, request kwargs)."""
    d, e, m = ids["dataset"], ids["experiment"], ids["model"]
    return [
        ("GET", f"/api/v1/datasets/{d}", {}),
        ("POST", f"/api/v1/datasets/{d}/validate", {}),
        ("DELETE", f"/api/v1/datasets/{d}", {}),
        ("POST", "/api/v1/experiments", {"json": classification_payload(d)}),
        ("GET", f"/api/v1/experiments/{e}", {}),
        ("GET", f"/api/v1/experiments/{e}/results", {}),
        ("GET", f"/api/v1/models/{m}", {}),
        ("POST", f"/api/v1/models/{m}/approve", {"json": {"confirm": True}}),
        ("POST", f"/api/v1/models/{m}/revoke", {"json": {"confirm": True}}),
        ("POST", f"/api/v1/models/{m}/predict", {"json": {"instances": [INSTANCE]}}),
    ]


def test_every_foreign_id_is_a_404(world: World) -> None:
    for method, path, kwargs in attempts(world.ids):
        response = world.bob.request(method, path, **kwargs)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_foreign_id_looks_exactly_like_a_missing_one(world: World) -> None:
    """If these differed, an attacker could tell real IDs from made-up ones."""
    fake = {"dataset": "ds_" + "0" * 32, "experiment": "ex_" + "0" * 32, "model": "md_" + "0" * 32}
    for (method, path, kwargs), (_, fake_path, fake_kwargs) in zip(
        attempts(world.ids), attempts(fake), strict=True
    ):
        foreign = world.bob.request(method, path, **kwargs)
        missing = world.bob.request(method, fake_path, **fake_kwargs)
        assert foreign.status_code == missing.status_code, path

        def strip(response: Any) -> dict[str, Any]:
            error = response.json()["error"]
            return {k: v for k, v in error.items() if k != "request_id"}

        assert strip(foreign) == strip(missing), path
        assert set(foreign.headers) - {"x-request-id"} == set(missing.headers) - {"x-request-id"}


def test_lists_only_show_your_own_resources(world: World) -> None:
    assert [m["model_id"] for m in world.alice.get("/api/v1/models").json()] == [world.ids["model"]]
    assert world.bob.get("/api/v1/models").json() == []


def test_failed_attempts_change_nothing(world: World) -> None:
    for method, path, kwargs in attempts(world.ids):
        world.bob.request(method, path, **kwargs)
    ids = world.ids
    assert world.alice.get(f"/api/v1/datasets/{ids['dataset']}").json()["status"] == "READY"
    assert world.alice.get(f"/api/v1/models/{ids['model']}").json()["approval_status"] == "APPROVED"
    assert world.alice.get(f"/api/v1/experiments/{ids['experiment']}").status_code == 200
    predicted = world.alice.post(
        f"/api/v1/models/{ids['model']}/predict", json={"instances": [INSTANCE]}
    )
    assert predicted.status_code == 200
    experiments_after = world.alice.get(f"/api/v1/experiments/{ids['experiment']}").json()
    assert experiments_after["status"] == "SUCCEEDED"


def test_users_have_separate_resources_with_their_own_ids(world: World) -> None:
    bobs = ready_dataset(world.bob, classification_csv())
    assert bobs != world.ids["dataset"]
    assert world.bob.get(f"/api/v1/datasets/{bobs}").status_code == 200
    assert world.alice.get(f"/api/v1/datasets/{bobs}").status_code == 404
    assert world.alice.delete(f"/api/v1/datasets/{bobs}").status_code == 404
    assert world.bob.get(f"/api/v1/datasets/{bobs}").status_code == 200


def test_stored_files_are_kept_under_the_owners_own_folder(
    world: World, alice: TestUser, tmp_path: Any
) -> None:
    dataset_folder = tmp_path / "storage" / "datasets" / alice.user_id / world.ids["dataset"]
    assert (dataset_folder / "source.csv").is_file()


def test_a_token_cannot_be_swapped_to_act_as_someone_else(
    world: World, anonymous_client: TestClient, alice: TestUser
) -> None:
    """Identity comes only from the token; nothing in the request can name another user."""
    forged = {**alice.headers, "X-User-Id": "someone-else", "X-Owner-Id": "someone-else"}
    response = anonymous_client.get(f"/api/v1/models/{world.ids['model']}", headers=forged)
    assert response.status_code == 200  # still alice, extra headers ignored
    assert response.json()["model_id"] == world.ids["model"]
