"""Deleting datasets (with everything derived from them) and revoking approved models."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_storage
from app.core.time import utc_now
from app.db import experiments as experiment_repo
from app.db.models import (
    AuditEvent,
    Dataset,
    Experiment,
    ExperimentRun,
    RegisteredModel,
)
from app.services import models as model_service
from app.services.models import clear_model_cache
from app.services.storage import LocalStorage
from tests.data import (
    classification_csv,
    insert_experiment,
    ready_dataset,
    regression_csv,
    regression_payload,
    trained_model_id,
    upload_dataset,
)

INSTANCE = {"x1": 1.0, "x2": 0.0, "color": "red"}
FAST = {"algorithms": ["logistic_regression", "decision_tree"]}


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    clear_model_cache()


def approve(client: TestClient, model_id: str) -> Any:
    return client.post(f"/api/v1/models/{model_id}/approve", json={"confirm": True})


def revoke(client: TestClient, model_id: str) -> Any:
    return client.post(f"/api/v1/models/{model_id}/revoke", json={"confirm": True})


def predict(client: TestClient, model_id: str) -> Any:
    return client.post(f"/api/v1/models/{model_id}/predict", json={"instances": [INSTANCE]})


def count(session_factory: sessionmaker[Session], table: type) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(table)) or 0)


def files_under(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# --- deleting a dataset -------------------------------------------------------------------------


def test_deleting_a_dataset_removes_everything_derived_from_it(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    tmp_path: Path,
    alice: Any,
) -> None:
    doomed = ready_dataset(client, classification_csv())
    model_id = trained_model_id(client, session_factory, storage, b"", dataset_id=doomed, **FAST)
    experiment_id = client.get(f"/api/v1/models/{model_id}").json()["experiment_id"]
    keep = ready_dataset(client, regression_csv(), "keep.csv")
    kept_model = trained_model_id(
        client, session_factory, storage, b"", regression_payload, dataset_id=keep
    )
    root = tmp_path / "storage"
    assert files_under(root / "models" / model_id)

    assert client.delete(f"/api/v1/datasets/{doomed}").status_code == 204

    for path in (
        f"/api/v1/datasets/{doomed}",
        f"/api/v1/experiments/{experiment_id}",
        f"/api/v1/experiments/{experiment_id}/results",
        f"/api/v1/models/{model_id}",
    ):
        assert client.get(path).status_code == 404, path
    assert [m["model_id"] for m in client.get("/api/v1/models").json()] == [kept_model]
    assert not files_under(root / "datasets" / alice.user_id / doomed)
    assert not (root / "models" / model_id).exists()

    # The other dataset, its model and its files are untouched.
    assert client.get(f"/api/v1/datasets/{keep}").json()["status"] == "READY"
    assert client.get(f"/api/v1/models/{kept_model}").status_code == 200
    assert files_under(root / "datasets" / alice.user_id / keep)
    assert files_under(root / "models" / kept_model)

    with session_factory() as session:
        assert session.get(Dataset, doomed) is None
        assert not list(session.scalars(select(Experiment).where(Experiment.dataset_id == doomed)))
        assert not list(
            session.scalars(
                select(ExperimentRun).where(ExperimentRun.experiment_id == experiment_id)
            )
        )
        assert not list(
            session.scalars(select(RegisteredModel).where(RegisteredModel.dataset_id == doomed))
        )


def test_deleting_twice_is_a_404(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 404


def test_deleting_an_unvalidated_or_rejected_dataset_works(
    client: TestClient, tmp_path: Path
) -> None:
    uploaded = upload_dataset(client, classification_csv(), "a.csv")
    rejected = upload_dataset(client, b"\n", "b.csv")
    client.post(f"/api/v1/datasets/{rejected}/validate")
    for dataset_id in (uploaded, rejected):
        assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
    assert not files_under(tmp_path / "storage")


def test_a_loaded_model_is_forgotten_when_its_dataset_is_deleted(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    model_id = trained_model_id(
        client, session_factory, storage, b"", dataset_id=dataset_id, **FAST
    )
    approve(client, model_id)
    assert predict(client, model_id).status_code == 200
    assert model_id in model_service._cache
    client.delete(f"/api/v1/datasets/{dataset_id}")
    assert model_id not in model_service._cache
    assert predict(client, model_id).status_code == 404


def test_a_running_experiment_blocks_deletion(
    client: TestClient, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    with session_factory() as session:
        insert_experiment(
            session, dataset_id, "ex_busy", utc_now(), status="RUNNING", started_at=utc_now()
        )
    blocked = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "STATE_CONFLICT"
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 200
    assert files_under(tmp_path / "storage")

    with session_factory() as session:  # the experiment finishes
        busy = session.get(Experiment, "ex_busy")
        assert busy is not None
        experiment_repo.finish_experiment(session, busy, status="FAILED", error_summary="done")  # type: ignore[arg-type]
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204


def test_queued_experiments_are_deleted_with_their_dataset(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    payload = {
        "dataset_id": dataset_id,
        "task": "classification",
        "target_column": "label",
        "algorithms": ["decision_tree"],
    }
    experiment_id = client.post("/api/v1/experiments", json=payload).json()["experiment_id"]
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
    assert client.get(f"/api/v1/experiments/{experiment_id}").status_code == 404
    assert count(session_factory, Experiment) == 0


def test_a_file_cleanup_failure_after_the_database_commit_is_not_an_error(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    class CannotDelete(LocalStorage):
        def delete_prefix(self, prefix: str) -> None:
            raise OSError("disk unplugged")

    dataset_id = ready_dataset(client, classification_csv())
    app.dependency_overrides[get_storage] = lambda: CannotDelete(tmp_path / "storage")
    response = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert response.status_code == 204  # the records are gone; only unreachable files remain
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert "disk" not in response.text


def test_deletion_is_audited(
    client: TestClient, session_factory: sessionmaker[Session], alice: Any
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    client.delete(f"/api/v1/datasets/{dataset_id}")
    with session_factory() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "dataset.delete"))
    assert event is not None
    assert (event.actor_id, event.resource_id, event.outcome) == (
        alice.user_id,
        dataset_id,
        "success",
    )


# --- revoking a model ---------------------------------------------------------------------------


@pytest.fixture
def model_id(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> str:
    return trained_model_id(client, session_factory, storage, classification_csv(), **FAST)


def test_revoking_stops_predictions_immediately(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    assert predict(client, model_id).status_code == 200  # also loads it into the cache
    response = revoke(client, model_id)
    assert response.status_code == 200 and response.json()["approval_status"] == "REVOKED"
    blocked = predict(client, model_id)
    assert blocked.status_code == 409
    assert "revoked" in blocked.json()["error"]["message"]
    assert client.get(f"/api/v1/models/{model_id}").json()["approval_status"] == "REVOKED"


def test_revoking_is_idempotent_and_only_for_approved_models(
    client: TestClient, model_id: str
) -> None:
    pending = revoke(client, model_id)
    assert pending.status_code == 409 and pending.json()["error"]["code"] == "STATE_CONFLICT"
    approve(client, model_id)
    assert revoke(client, model_id).status_code == 200
    assert revoke(client, model_id).status_code == 200  # no error the second time


def test_a_revoked_model_cannot_be_approved_again(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    revoke(client, model_id)
    again = approve(client, model_id)
    assert again.status_code == 409
    assert client.get(f"/api/v1/models/{model_id}").json()["approval_status"] == "REVOKED"


@pytest.mark.parametrize("body", [{}, {"confirm": False}, {"confirm": "yes"}])
def test_revoking_must_be_explicit(client: TestClient, model_id: str, body: dict[str, Any]) -> None:
    approve(client, model_id)
    assert client.post(f"/api/v1/models/{model_id}/revoke", json=body).status_code == 422
    assert client.get(f"/api/v1/models/{model_id}").json()["approval_status"] == "APPROVED"


def test_a_new_version_is_independent_of_a_revoked_one(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage, model_id: str
) -> None:
    approve(client, model_id)
    revoke(client, model_id)
    dataset_id = client.get(f"/api/v1/models/{model_id}").json()["dataset_id"]
    second = trained_model_id(client, session_factory, storage, b"", dataset_id=dataset_id, **FAST)
    body = client.get(f"/api/v1/models/{second}").json()
    assert body["version"] == 2 and body["approval_status"] == "PENDING"
    approve(client, second)
    assert predict(client, second).status_code == 200
    assert predict(client, model_id).status_code == 409


def test_approval_changes_are_audited(
    client: TestClient, session_factory: sessionmaker[Session], model_id: str, alice: Any
) -> None:
    approve(client, model_id)
    revoke(client, model_id)
    with session_factory() as session:
        actions = [
            (e.action, e.actor_id, e.resource_id)
            for e in session.scalars(
                select(AuditEvent).where(AuditEvent.action.in_(["model.approve", "model.revoke"]))
            )
        ]
    assert sorted(actions) == sorted(
        [("model.approve", alice.user_id, model_id), ("model.revoke", alice.user_id, model_id)]
    )
