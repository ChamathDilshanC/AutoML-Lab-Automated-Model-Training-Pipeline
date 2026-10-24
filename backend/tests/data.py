"""Small deterministic datasets and helpers shared by the API and worker tests."""

from collections.abc import Callable

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.services.storage import StorageAdapter
from worker.jobs import process_next


def classification_csv(rows: int = 80) -> bytes:
    rng = np.random.default_rng(0)
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    color = rng.choice(["red", "green", "blue"], size=rows)
    label = np.where(x1 + 0.3 * x2 + rng.normal(scale=0.3, size=rows) > 0, "pos", "neg")
    df = pd.DataFrame({"x1": x1, "x2": x2, "color": color, "label": label})
    return df.to_csv(index=False).encode()


def regression_csv(rows: int = 80) -> bytes:
    rng = np.random.default_rng(1)
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    group = rng.choice(["a", "b"], size=rows)
    price = 3 * x1 - 2 * x2 + np.where(group == "a", 1.0, -1.0) + rng.normal(scale=0.1, size=rows)
    return (
        pd.DataFrame({"x1": x1, "x2": x2, "group": group, "price": price})
        .to_csv(index=False)
        .encode()
    )


def rare_class_csv() -> bytes:
    """Passes dataset validation, but class `c` has a single row, which the worker rejects."""
    rng = np.random.default_rng(2)
    labels = ["a"] * 20 + ["b"] * 19 + ["c"]
    return pd.DataFrame({"x": rng.normal(size=40), "label": labels}).to_csv(index=False).encode()


def upload_dataset(client: TestClient, content: bytes, filename: str = "data.csv") -> str:
    response = client.post("/api/v1/datasets", files={"file": (filename, content, "text/csv")})
    assert response.status_code == 201, response.text
    return str(response.json()["dataset_id"])


def ready_dataset(client: TestClient, content: bytes, filename: str = "data.csv") -> str:
    dataset_id = upload_dataset(client, content, filename)
    report = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert report.json()["status"] == "READY", report.text
    return dataset_id


def classification_payload(dataset_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "dataset_id": dataset_id,
        "task": "classification",
        "target_column": "label",
        "metric": "f1",
        "algorithms": ["logistic_regression", "decision_tree", "random_forest"],
    }
    payload.update(overrides)
    return payload


def regression_payload(dataset_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "dataset_id": dataset_id,
        "task": "regression",
        "target_column": "price",
        "metric": "rmse",
        "algorithms": ["linear_regression", "decision_tree"],
    }
    payload.update(overrides)
    return payload


def trained_model_id(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: StorageAdapter,
    content: bytes,
    payload_for: Callable[..., dict[str, object]] = classification_payload,
    dataset_id: str | None = None,
    **overrides: object,
) -> str:
    """Run a real experiment through the worker and return the registered model's ID."""
    dataset_id = dataset_id or ready_dataset(client, content)
    created = client.post("/api/v1/experiments", json=payload_for(dataset_id, **overrides))
    assert created.status_code == 202, created.text
    experiment_id = created.json()["experiment_id"]
    assert process_next(session_factory, storage) is True
    board = client.get(f"/api/v1/experiments/{experiment_id}/results").json()
    assert board["model_id"], board
    return str(board["model_id"])
