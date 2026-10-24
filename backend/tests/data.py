"""Small deterministic datasets and helpers shared by the API and worker tests."""

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient


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
