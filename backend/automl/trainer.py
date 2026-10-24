"""Training of allowlisted estimators.

Only estimators listed in `ESTIMATORS` can be trained; algorithm names are looked up, never
imported from user input. Hyper-parameter search runs on training data only.
"""

import platform
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import GridSearchCV, KFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from automl.evaluator import DEFAULT_METRIC, get_metric, scoring_for
from automl.preprocessing import build_preprocessor
from automl.tasks import Task


@dataclass(frozen=True)
class EstimatorSpec:
    factory: Callable[[int], Any]  # random_state -> unfitted estimator
    param_grid: dict[str, list[Any]]  # keys are estimator parameter names


ESTIMATORS: dict[Task, dict[str, EstimatorSpec]] = {
    "classification": {
        "logistic_regression": EstimatorSpec(
            lambda seed: LogisticRegression(max_iter=1000, random_state=seed),
            {"C": [0.1, 1.0, 10.0]},
        ),
        "decision_tree": EstimatorSpec(
            lambda seed: DecisionTreeClassifier(random_state=seed),
            {"max_depth": [3, 5, None]},
        ),
        "random_forest": EstimatorSpec(
            lambda seed: RandomForestClassifier(random_state=seed),
            {"n_estimators": [50, 100], "max_depth": [None, 5]},
        ),
    },
    "regression": {
        "linear_regression": EstimatorSpec(lambda seed: LinearRegression(), {}),
        "decision_tree": EstimatorSpec(
            lambda seed: DecisionTreeRegressor(random_state=seed),
            {"max_depth": [3, 5, None]},
        ),
        "random_forest": EstimatorSpec(
            lambda seed: RandomForestRegressor(random_state=seed),
            {"n_estimators": [50, 100], "max_depth": [None, 5]},
        ),
    },
}


@dataclass(frozen=True)
class TrainedModel:
    """A fitted pipeline plus the information needed to reproduce and describe it."""

    pipeline: Pipeline
    task: Task
    algorithm: str
    best_params: dict[str, Any]
    cv_score: float | None  # in the metric's natural units; None when nothing was tuned
    cv_folds: int | None
    tuning_metric: str
    random_state: int
    feature_names: list[str]
    library_versions: dict[str, str]


def available_algorithms(task: Task) -> list[str]:
    return sorted(ESTIMATORS[task])


def library_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
    }


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    task: Task,
    algorithm: str,
    *,
    metric: str | None = None,
    random_state: int = 42,
    cv: int = 3,
) -> TrainedModel:
    """Fit preprocessing and the chosen estimator on training data only.

    The preprocessing and estimator form one pipeline, so cross-validation refits imputers,
    scalers and encoders on each training fold. The best configuration is refit on all of
    `X_train`. The held-out test set is not an input to this function.
    """
    if algorithm not in ESTIMATORS[task]:
        raise ValueError(
            f"Unsupported algorithm {algorithm!r} for {task}; "
            f"expected one of {available_algorithms(task)}."
        )
    spec = ESTIMATORS[task][algorithm]
    metric = metric or DEFAULT_METRIC[task]
    metric_spec = get_metric(task, metric)

    pipeline = Pipeline(
        [
            ("preprocess", build_preprocessor(X_train)),
            ("model", spec.factory(random_state)),
        ]
    )

    best_params: dict[str, Any] = {}
    cv_score: float | None = None
    folds: int | None = None

    if not spec.param_grid:
        pipeline.fit(X_train, y_train)
        fitted = pipeline
    else:
        folds, splitter = _cv_splitter(y_train, task, cv, random_state)
        n_classes = int(y_train.nunique()) if task == "classification" else None
        search = GridSearchCV(
            pipeline,
            {f"model__{name}": values for name, values in spec.param_grid.items()},
            scoring=scoring_for(task, metric, n_classes),
            cv=splitter,
            refit=True,
        )
        search.fit(X_train, y_train)
        fitted = search.best_estimator_
        best_params = {
            key.removeprefix("model__"): value for key, value in search.best_params_.items()
        }
        score = float(search.best_score_)
        cv_score = score if metric_spec.higher_is_better else -score

    return TrainedModel(
        pipeline=fitted,
        task=task,
        algorithm=algorithm,
        best_params=best_params,
        cv_score=cv_score,
        cv_folds=folds,
        tuning_metric=metric,
        random_state=random_state,
        feature_names=[str(column) for column in X_train.columns],
        library_versions=library_versions(),
    )


def _cv_splitter(
    y_train: pd.Series, task: Task, cv: int, random_state: int
) -> tuple[int, StratifiedKFold | KFold]:
    """Seeded cross-validation splitter with a fold count the training data can support."""
    if task == "classification":
        folds = min(cv, int(y_train.value_counts().min()))
        if folds < 2:
            raise ValueError("Not enough rows per class for cross-validation.")
        return folds, StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    folds = min(cv, len(y_train))
    if folds < 2:
        raise ValueError("Not enough rows for cross-validation.")
    return folds, KFold(n_splits=folds, shuffle=True, random_state=random_state)
