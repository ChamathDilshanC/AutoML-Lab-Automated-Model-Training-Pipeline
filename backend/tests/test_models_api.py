"""API tests for the model registry and prediction endpoint, using models the real worker made."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.security import get_owner_id
from app.db.models import RegisteredModel
from app.services.models import clear_model_cache
from app.services.storage import LocalStorage
from automl import registry as engine_registry
from tests.data import (
    classification_csv,
    ready_dataset,
    regression_csv,
    regression_payload,
    trained_model_id,
)

GOOD_INSTANCE = {"x1": 1.2, "x2": -0.3, "color": "red"}


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    clear_model_cache()
    yield
    clear_model_cache()


@pytest.fixture
def model_id(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> str:
    return trained_model_id(
        client,
        session_factory,
        storage,
        classification_csv(),
        algorithms=["logistic_regression", "decision_tree"],  # fast; the winner is registered
    )


def approve(client: TestClient, model_id: str):
    return client.post(f"/api/v1/models/{model_id}/approve", json={"confirm": True})


def predict(client: TestClient, model_id: str, instances: object):
    return client.post(f"/api/v1/models/{model_id}/predict", json={"instances": instances})


# --- registration -------------------------------------------------------------------------------


def test_a_succeeded_experiment_registers_a_pending_model(
    client: TestClient, model_id: str, tmp_path: Path
) -> None:
    body = client.get(f"/api/v1/models/{model_id}").json()
    assert body["model_id"] == model_id
    assert body["version"] == 1
    assert body["approval_status"] == "PENDING" and body["approved_at"] is None
    assert body["task"] == "classification" and body["target_column"] == "label"
    assert body["classes"] == ["neg", "pos"]
    assert body["metric"] == "f1" and body["metrics"]["f1"] > 0.5
    assert body["dataset_filename"] == "data.csv"
    assert [f["name"] for f in body["feature_schema"]] == ["x1", "x2", "color"]
    assert "label" not in [f["name"] for f in body["feature_schema"]]
    assert body["created_at"].endswith("Z")
    assert "artifact_key" not in body and "artifact_sha256" not in body

    folder = tmp_path / "storage" / "models" / model_id / "1"
    assert (folder / "model.joblib").stat().st_size == body["artifact_bytes"]
    metadata = json.loads((folder / "metadata.json").read_text())
    assert metadata["model_id"] == model_id and metadata["feature_schema"] == body["feature_schema"]
    assert metadata["library_versions"] == body["library_versions"]


def test_the_registered_model_is_the_leaderboard_winner(
    client: TestClient, session_factory: sessionmaker[Session], model_id: str
) -> None:
    with session_factory() as session:
        model = session.get(RegisteredModel, model_id)
        assert model is not None
        board = client.get(f"/api/v1/experiments/{model.experiment_id}/results").json()
    winner = board["runs"][0]
    assert board["model_id"] == model_id
    assert winner["run_id"] == board["selected_run_id"] == model.run_id
    assert model.algorithm == winner["algorithm"] and model.metrics == winner["metrics"]


def test_rerunning_the_same_experiment_creates_a_new_immutable_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    tmp_path: Path,
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    first = trained_model_id(
        client, session_factory, storage, b"", dataset_id=dataset_id, algorithms=["decision_tree"]
    )
    second = trained_model_id(
        client, session_factory, storage, b"", dataset_id=dataset_id, algorithms=["decision_tree"]
    )
    assert first != second
    assert client.get(f"/api/v1/models/{first}").json()["version"] == 1
    assert client.get(f"/api/v1/models/{second}").json()["version"] == 2
    assert (tmp_path / "storage" / "models" / first / "1" / "model.joblib").is_file()
    assert (tmp_path / "storage" / "models" / second / "2" / "model.joblib").is_file()
    listed = [m["model_id"] for m in client.get("/api/v1/models").json()]
    assert listed == [second, first]  # newest first


def test_a_different_target_starts_again_at_version_one(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    classification = trained_model_id(client, session_factory, storage, classification_csv())
    regression = trained_model_id(
        client, session_factory, storage, regression_csv(), payload_for=regression_payload
    )
    assert client.get(f"/api/v1/models/{classification}").json()["version"] == 1
    assert client.get(f"/api/v1/models/{regression}").json()["version"] == 1


def test_models_are_listed_and_owner_scoped(
    app: FastAPI, client: TestClient, model_id: str
) -> None:
    assert [m["model_id"] for m in client.get("/api/v1/models").json()] == [model_id]
    app.dependency_overrides[get_owner_id] = lambda: "someone-else"
    assert client.get("/api/v1/models").json() == []
    for response in (
        client.get(f"/api/v1/models/{model_id}"),
        approve(client, model_id),
        predict(client, model_id, [GOOD_INSTANCE]),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_model_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/models/md_missing").status_code == 404


# --- approval -----------------------------------------------------------------------------------


@pytest.mark.parametrize("body", [{}, {"confirm": False}, {"confirm": "yes"}])
def test_approval_must_be_explicit(client: TestClient, model_id: str, body: dict) -> None:
    response = client.post(f"/api/v1/models/{model_id}/approve", json=body)
    assert response.status_code == 422
    assert client.get(f"/api/v1/models/{model_id}").json()["approval_status"] == "PENDING"


def test_approving_is_idempotent(client: TestClient, model_id: str) -> None:
    first = approve(client, model_id)
    assert first.status_code == 200
    assert first.json()["approval_status"] == "APPROVED"
    approved_at = first.json()["approved_at"]
    assert approved_at.endswith("Z")
    second = approve(client, model_id)
    assert second.json()["approved_at"] == approved_at


# --- prediction ---------------------------------------------------------------------------------


def test_predictions_require_an_approved_model(client: TestClient, model_id: str) -> None:
    response = predict(client, model_id, [GOOD_INSTANCE])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"


def test_classification_prediction(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    response = predict(
        client,
        model_id,
        [
            {"x1": 2.5, "x2": 0.0, "color": "red"},
            {"x1": -2.5, "x2": 0.0, "color": "blue"},
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["predictions"] == ["pos", "neg"]
    assert body["model_id"] == model_id and body["model_version"] == 1
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["classes"] == ["neg", "pos"]
    for probabilities in body["probabilities"]:
        assert set(probabilities) == {"neg", "pos"}
        assert sum(probabilities.values()) == pytest.approx(1.0, abs=1e-4)
    assert body["probabilities"][0]["pos"] > 0.5 > body["probabilities"][1]["pos"]


def test_predictions_are_repeatable(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    first = predict(client, model_id, [GOOD_INSTANCE]).json()
    second = predict(client, model_id, [GOOD_INSTANCE]).json()
    assert first["predictions"] == second["predictions"]
    assert first["probabilities"] == second["probabilities"]


def test_regression_prediction(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    model_id = trained_model_id(
        client, session_factory, storage, regression_csv(), payload_for=regression_payload
    )
    approve(client, model_id)
    body = predict(client, model_id, [{"x1": 0.5, "x2": 0.1, "group": "a"}]).json()
    assert body["classes"] is None and body["probabilities"] is None
    assert body["predictions"][0] == pytest.approx(3 * 0.5 - 2 * 0.1 + 1.0, abs=0.5)


def test_null_and_unseen_values_are_handled(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    response = predict(
        client,
        model_id,
        [{"x1": None, "x2": 0.2, "color": None}, {**GOOD_INSTANCE, "color": "teal"}],
    )
    assert response.status_code == 200
    assert len(response.json()["predictions"]) == 2


def error_fields(response) -> set[str]:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["request_id"] == response.headers["X-Request-ID"]
    return {detail["field"] for detail in error["details"]}


def test_unknown_fields_are_rejected(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    response = predict(client, model_id, [{**GOOD_INSTANCE, "label": "pos"}])
    assert error_fields(response) == {"instances[0].label"}


def test_missing_fields_are_rejected(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    response = predict(client, model_id, [GOOD_INSTANCE, {"x1": 1.0, "color": "red"}])
    assert error_fields(response) == {"instances[1].x2"}


@pytest.mark.parametrize("value", ["1.0", True, [1], {"a": 1}, 1e999])
def test_wrong_types_are_rejected(client: TestClient, model_id: str, value: object) -> None:
    approve(client, model_id)
    response = client.post(
        f"/api/v1/models/{model_id}/predict",
        content=json.dumps({"instances": [{**GOOD_INSTANCE, "x1": value}]}),
        headers={"Content-Type": "application/json"},
    )
    assert error_fields(response) == {"instances[0].x1"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"instances": []},
        {"instances": "not a list"},
        {"instances": [1, 2]},
        {"instances": [["x1", 1]]},
        [GOOD_INSTANCE],
    ],
)
def test_malformed_bodies_use_the_error_envelope(
    client: TestClient, model_id: str, body: object
) -> None:
    approve(client, model_id)
    response = client.post(f"/api/v1/models/{model_id}/predict", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_json_is_rejected(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    response = client.post(
        f"/api/v1/models/{model_id}/predict",
        content="{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "not json" not in response.text


def test_error_messages_never_echo_input_values(client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    response = predict(client, model_id, [{**GOOD_INSTANCE, "x1": "SECRET_VALUE_123"}])
    assert response.status_code == 422
    assert "SECRET_VALUE_123" not in response.text


def test_batch_size_is_limited(app: FastAPI, client: TestClient, model_id: str) -> None:
    approve(client, model_id)
    app.dependency_overrides[get_settings] = lambda: Settings(max_prediction_batch=2)
    assert predict(client, model_id, [GOOD_INSTANCE] * 2).status_code == 200
    response = predict(client, model_id, [GOOD_INSTANCE] * 3)
    assert error_fields(response) == {"instances"}


def test_a_model_from_another_scikit_learn_version_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], model_id: str
) -> None:
    approve(client, model_id)
    with session_factory() as session:
        model = session.get(RegisteredModel, model_id)
        assert model is not None
        model.library_versions = {**model.library_versions, "scikit-learn": "0.0.1"}
        session.commit()
    response = predict(client, model_id, [GOOD_INSTANCE])
    assert response.status_code == 409
    assert "scikit-learn" in response.json()["error"]["message"]


# --- artifact trust (ADR 0002) ------------------------------------------------------------------


def test_a_tampered_artifact_is_never_deserialised(
    client: TestClient, model_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approve(client, model_id)
    artifact = tmp_path / "storage" / "models" / model_id / "1" / "model.joblib"
    artifact.write_bytes(b"not the artifact we wrote")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("joblib.load was called on an unverified artifact")

    monkeypatch.setattr(engine_registry.joblib, "load", forbidden)
    response = predict(client, model_id, [GOOD_INSTANCE])
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "integrity" in response.json()["error"]["message"]


def test_a_missing_artifact_is_a_clean_error(
    client: TestClient, model_id: str, tmp_path: Path
) -> None:
    approve(client, model_id)
    (tmp_path / "storage" / "models" / model_id / "1" / "model.joblib").unlink()
    response = predict(client, model_id, [GOOD_INSTANCE])
    assert response.status_code == 500
    assert str(tmp_path) not in response.text


def test_joblib_only_ever_loads_the_verified_artifact_never_request_input(
    client: TestClient, model_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    approve(client, model_id)
    loaded: list[object] = []
    real_load = engine_registry.joblib.load

    def spy(file: object, *args: object, **kwargs: object) -> object:
        loaded.append(file)
        return real_load(file, *args, **kwargs)

    monkeypatch.setattr(engine_registry.joblib, "load", spy)
    hostile = {"x1": 1.0, "x2": 1.0, "color": "cos\nsystem (S'echo pwned'\ntR."}
    for _ in range(3):
        assert predict(client, model_id, [hostile]).status_code == 200
    assert len(loaded) == 1  # the artifact, once; later requests reuse the loaded pipeline


def test_a_loaded_pipeline_is_reused_even_if_the_file_disappears(
    client: TestClient, model_id: str, tmp_path: Path
) -> None:
    approve(client, model_id)
    assert predict(client, model_id, [GOOD_INSTANCE]).status_code == 200
    (tmp_path / "storage" / "models" / model_id / "1" / "model.joblib").unlink()
    assert predict(client, model_id, [GOOD_INSTANCE]).status_code == 200
