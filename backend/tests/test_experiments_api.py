"""API tests for experiment configuration and retrieval (training is tested in test_worker)."""

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_owner_id
from tests.data import (
    classification_csv,
    classification_payload,
    ready_dataset,
    regression_csv,
    regression_payload,
    upload_dataset,
)


def create(client: TestClient, payload: dict[str, object], **headers: str):
    return client.post("/api/v1/experiments", json=payload, headers=headers)


# --- options ------------------------------------------------------------------------------------


def test_options_list_the_allowlist_and_metric_directions(client: TestClient) -> None:
    response = client.get("/api/v1/experiments/options")
    assert response.status_code == 200
    body = response.json()
    assert body["classification"]["algorithms"] == [
        "decision_tree",
        "logistic_regression",
        "random_forest",
    ]
    assert body["classification"]["default_metric"] == "f1"
    directions = {m["name"]: m["higher_is_better"] for m in body["regression"]["metrics"]}
    assert directions == {"mae": False, "rmse": False, "r2": True}


# --- create and read ----------------------------------------------------------------------------


def test_create_queues_the_experiment(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    response = create(client, classification_payload(dataset_id))
    assert response.status_code == 202
    assert response.headers["X-Request-ID"].startswith("req_")
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["metric"] == "f1"
    assert body["random_seed"] == 42 and body["test_size"] == 0.2
    assert body["created_at"].endswith("Z")
    assert body["started_at"] is None and body["finished_at"] is None

    fetched = client.get(f"/api/v1/experiments/{body['experiment_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_metric_defaults_per_task(client: TestClient) -> None:
    dataset_id = ready_dataset(client, regression_csv())
    payload = regression_payload(dataset_id)
    del payload["metric"]
    assert create(client, payload).json()["metric"] == "rmse"


def test_duplicate_algorithms_are_collapsed_in_order(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    payload = classification_payload(
        dataset_id, algorithms=["random_forest", "decision_tree", "random_forest"]
    )
    assert create(client, payload).json()["algorithms"] == ["random_forest", "decision_tree"]


def test_results_are_not_available_until_the_experiment_finishes(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = create(client, classification_payload(dataset_id)).json()["experiment_id"]
    response = client.get(f"/api/v1/experiments/{experiment_id}/results")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"


# --- configuration validation -------------------------------------------------------------------


def invalid_fields(response) -> set[str]:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    return {detail["field"] for detail in error["details"]}


def test_unknown_target_column_is_rejected(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    response = create(client, classification_payload(dataset_id, target_column="nope"))
    assert invalid_fields(response) == {"target_column"}
    assert "not found" in response.json()["error"]["message"]


def test_regression_needs_a_numeric_target(client: TestClient) -> None:
    dataset_id = ready_dataset(client, regression_csv())
    response = create(client, regression_payload(dataset_id, target_column="group"))
    assert invalid_fields(response) == {"target_column"}
    assert "numeric" in response.json()["error"]["message"]


def test_metric_must_fit_the_task(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    assert invalid_fields(create(client, classification_payload(dataset_id, metric="rmse"))) == {
        "metric"
    }


@pytest.mark.parametrize(
    "algorithms", [["os.system"], ["linear_regression"], ["random_forest", "x"]]
)
def test_algorithms_must_be_on_the_allowlist(client: TestClient, algorithms: list[str]) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    response = create(client, classification_payload(dataset_id, algorithms=algorithms))
    assert invalid_fields(response) == {"algorithms"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"algorithms": []},
        {"test_size": 0.9},
        {"test_size": 0.0},
        {"random_seed": -1},
        {"task": "clustering"},
        {"target_column": ""},
    ],
)
def test_malformed_payloads_use_the_error_envelope(
    client: TestClient, overrides: dict[str, object]
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    response = create(client, classification_payload(dataset_id, **overrides))
    assert response.status_code == 422
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_target_with_missing_values_or_one_value_is_rejected(client: TestClient) -> None:
    df = pd.read_csv(pd.io.common.BytesIO(classification_csv()))
    df.loc[0, "label"] = None
    df["constant"] = 1
    dataset_id = ready_dataset(client, df.to_csv(index=False).encode())
    assert invalid_fields(create(client, classification_payload(dataset_id))) == {"target_column"}
    assert invalid_fields(
        create(client, classification_payload(dataset_id, target_column="constant"))
    ) == {"target_column"}


# --- dataset state and ownership ----------------------------------------------------------------


def test_unknown_dataset_is_404(client: TestClient) -> None:
    response = create(client, classification_payload("ds_missing"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_dataset_must_be_ready(client: TestClient) -> None:
    unvalidated = upload_dataset(client, classification_csv())
    response = create(client, classification_payload(unvalidated))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"

    rejected = upload_dataset(client, b"\n")
    client.post(f"/api/v1/datasets/{rejected}/validate")
    assert create(client, classification_payload(rejected)).status_code == 409


def test_other_owners_cannot_use_or_read_experiments(app: FastAPI, client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = create(client, classification_payload(dataset_id)).json()["experiment_id"]

    app.dependency_overrides[get_owner_id] = lambda: "someone-else"
    assert create(client, classification_payload(dataset_id)).status_code == 404
    assert client.get(f"/api/v1/experiments/{experiment_id}").status_code == 404
    assert client.get(f"/api/v1/experiments/{experiment_id}/results").status_code == 404


def test_unknown_experiment_is_404(client: TestClient) -> None:
    for path in ("/api/v1/experiments/ex_missing", "/api/v1/experiments/ex_missing/results"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


# --- idempotency --------------------------------------------------------------------------------


def test_same_idempotency_key_returns_the_same_experiment(client: TestClient) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    payload = classification_payload(dataset_id)
    first = create(client, payload, **{"Idempotency-Key": "abc-123"})
    second = create(client, payload, **{"Idempotency-Key": "abc-123"})
    other = create(client, payload, **{"Idempotency-Key": "xyz-789"})
    unkeyed = create(client, payload)
    assert first.status_code == second.status_code == 202
    assert first.json()["experiment_id"] == second.json()["experiment_id"]
    assert other.json()["experiment_id"] != first.json()["experiment_id"]
    assert unkeyed.json()["experiment_id"] not in {
        first.json()["experiment_id"],
        other.json()["experiment_id"],
    }


def test_browser_preflight_allows_the_idempotency_key_header(client: TestClient) -> None:
    """A browser blocks the POST unless the preflight allows every custom header it sends."""
    response = client.options(
        "/api/v1/experiments",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )
    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed and "content-type" in allowed
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
