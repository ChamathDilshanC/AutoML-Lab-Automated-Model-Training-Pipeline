"""Metrics, evaluation on held-out data, and ranking.

Classification precision, recall and F1 use weighted averaging for every class count, so binary
and multiclass tasks share one definition and labels may be strings.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)

from automl.tasks import Task


@dataclass(frozen=True)
class MetricSpec:
    name: str
    task: Task
    higher_is_better: bool
    scoring: str  # scikit-learn scorer name used when tuning with cross-validation


METRICS: dict[Task, dict[str, MetricSpec]] = {
    "classification": {
        "accuracy": MetricSpec("accuracy", "classification", True, "accuracy"),
        "precision": MetricSpec("precision", "classification", True, "precision_weighted"),
        "recall": MetricSpec("recall", "classification", True, "recall_weighted"),
        "f1": MetricSpec("f1", "classification", True, "f1_weighted"),
        "roc_auc": MetricSpec("roc_auc", "classification", True, "roc_auc"),
    },
    "regression": {
        "mae": MetricSpec("mae", "regression", False, "neg_mean_absolute_error"),
        "rmse": MetricSpec("rmse", "regression", False, "neg_root_mean_squared_error"),
        "r2": MetricSpec("r2", "regression", True, "r2"),
    },
}

DEFAULT_METRIC: dict[Task, str] = {"classification": "f1", "regression": "rmse"}


def get_metric(task: Task, name: str) -> MetricSpec:
    """Look up a metric for a task; unknown or wrong-task names raise `ValueError`."""
    try:
        return METRICS[task][name]
    except KeyError:
        raise ValueError(f"Metric {name!r} is not available for {task}.") from None


def scoring_for(task: Task, name: str, n_classes: int | None = None) -> str:
    """scikit-learn scorer name for cross-validated tuning with this metric."""
    spec = get_metric(task, name)
    if name == "roc_auc" and n_classes is not None and n_classes > 2:
        return "roc_auc_ovr_weighted"
    return spec.scoring


def evaluate(
    model: Any, X_test: pd.DataFrame, y_test: pd.Series, task: Task
) -> dict[str, float | None]:
    """Compute every metric for the task on held-out data.

    A metric that cannot be computed (for example ROC-AUC without probabilities, or when the test
    set lacks a class) is returned as `None`.
    """
    y_pred = model.predict(X_test)

    if task == "regression":
        return {
            "mae": float(mean_absolute_error(y_test, y_pred)),
            "rmse": float(root_mean_squared_error(y_test, y_pred)),
            "r2": float(r2_score(y_test, y_pred)),
        }

    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, average="weighted", zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, average="weighted", zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
        "roc_auc": _roc_auc(model, X_test, y_test),
    }


def _roc_auc(model: Any, X_test: pd.DataFrame, y_test: pd.Series) -> float | None:
    if not hasattr(model, "predict_proba"):
        return None
    classes = list(model.classes_)
    if y_test.nunique() < len(classes):
        return None  # ROC-AUC is undefined when the test set lacks a class
    try:
        probabilities = model.predict_proba(X_test)
        if len(classes) == 2:
            score = roc_auc_score(y_test, probabilities[:, 1])
        else:
            score = roc_auc_score(
                y_test, probabilities, multi_class="ovr", average="weighted", labels=classes
            )
    except ValueError:
        return None
    return float(score) if math.isfinite(score) else None


def rank_results(
    results: Mapping[str, Mapping[str, float | None]], task: Task, metric: str
) -> list[str]:
    """Order run names best first by `metric`, respecting its direction.

    Runs whose metric is missing or not finite are excluded. Ties are broken by run name so the
    order is deterministic.
    """
    spec = get_metric(task, metric)
    scored = [
        (name, value)
        for name, metrics in results.items()
        if (value := metrics.get(metric)) is not None and math.isfinite(value)
    ]
    scored.sort(key=lambda item: (-item[1] if spec.higher_is_better else item[1], item[0]))
    return [name for name, _ in scored]
