"""Model artifacts: serialisation, the feature schema, and strict validation of prediction input.

SECURITY: `joblib` uses pickle, and loading a pickle can run arbitrary code. `loads_pipeline` must
only ever receive bytes that this system wrote itself (docs/ADR/0002). Callers verify a stored
checksum first. Prediction *input* is never deserialised with joblib: it is plain JSON that
`instances_to_frame` validates against the feature schema.
"""

import hashlib
import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd

from automl.preprocessing import split_column_types
from automl.trainer import TrainedModel

# Proposed limits.
MAX_CATEGORIES = 50
MAX_STRING_LENGTH = 200
MAX_REPORTED_ISSUES = 20


@dataclass(frozen=True)
class FeatureSpec:
    """One input column of a model.

    `kind` is how the pipeline treats the column; `value_type` is the JSON type a caller must send.
    `categories` lists the values seen in training for string columns with few distinct values.
    """

    name: str
    kind: str  # "numeric" or "categorical"
    value_type: str  # "number", "string" or "boolean"
    categories: list[str] | None


def build_feature_schema(X_train: pd.DataFrame) -> list[dict[str, Any]]:
    """Describe the input columns of a model trained on `X_train` (the target is never in it)."""
    numeric, _ = split_column_types(X_train)
    schema = []
    for column in X_train.columns:
        if column in numeric:
            spec = FeatureSpec(str(column), "numeric", "number", None)
        elif pd.api.types.is_bool_dtype(X_train[column]):
            spec = FeatureSpec(str(column), "categorical", "boolean", None)
        else:
            values = sorted(str(v) for v in X_train[column].dropna().unique())
            categories = values if len(values) <= MAX_CATEGORIES else None
            spec = FeatureSpec(str(column), "categorical", "string", categories)
        schema.append(asdict(spec))
    return schema


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps_pipeline(pipeline: Any) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(pipeline, buffer)
    return buffer.getvalue()


def loads_pipeline(data: bytes) -> Any:
    """Load a pipeline written by `dumps_pipeline`. TRUSTED BYTES ONLY (see module docstring)."""
    return joblib.load(io.BytesIO(data))


def build_metadata(
    *,
    model_id: str,
    version: int,
    experiment_id: str,
    run_id: str,
    trained: TrainedModel,
    metric: str,
    metrics: Mapping[str, float | None],
    feature_schema: Sequence[Mapping[str, Any]],
    split_info: Mapping[str, Any],
    target_column: str,
    created_at: str,
) -> dict[str, Any]:
    """The `metadata.json` stored next to the artifact. Contains no data rows."""
    classes = getattr(trained.pipeline, "classes_", None)
    return {
        "model_id": model_id,
        "version": version,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "task": trained.task,
        "algorithm": trained.algorithm,
        "target_column": target_column,
        "metric": metric,
        "metrics": dict(metrics),
        "hyperparameters": trained.best_params,
        "feature_schema": [dict(spec) for spec in feature_schema],
        "classes": classes.tolist() if classes is not None else None,
        "preprocessing": {
            "numeric": {"imputer": "median", "scaler": "standard"},
            "categorical": {
                "imputer": "most_frequent",
                "encoder": "one_hot (unseen categories ignored)",
            },
            "numeric_columns": [s["name"] for s in feature_schema if s["kind"] == "numeric"],
            "categorical_columns": [
                s["name"] for s in feature_schema if s["kind"] == "categorical"
            ],
        },
        "split": dict(split_info),
        "random_state": trained.random_state,
        "library_versions": trained.library_versions,
        "created_at": created_at,
        "trained_on": "training split only (not refit on the test rows)",
    }


class InstanceValidationError(ValueError):
    """Prediction input does not match the feature schema. Issues name fields, never values."""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        super().__init__("Prediction input is invalid.")
        self.issues = issues


def _value_issue(spec: Mapping[str, Any], value: Any) -> str | None:
    """Why `value` is not acceptable for this feature, or None. `null` is always accepted."""
    if value is None:
        return None
    value_type = spec["value_type"]
    if value_type == "number":
        ok = isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
        return None if ok else "must be a finite number"
    if value_type == "boolean":
        return None if isinstance(value, bool) else "must be true or false"
    if not isinstance(value, str):
        return "must be a string"
    if len(value) > MAX_STRING_LENGTH:
        return f"must be at most {MAX_STRING_LENGTH} characters"
    return None


def instances_to_frame(
    schema: Sequence[Mapping[str, Any]], instances: Sequence[Mapping[str, Any]]
) -> pd.DataFrame:
    """Validate JSON instances strictly against `schema` and build the model's input frame.

    Every instance must contain exactly the schema's fields: unknown and missing fields are
    rejected. A value may be `null`, which the pipeline imputes from training statistics. Unseen
    category values are accepted (the encoder ignores them).
    """
    names = [spec["name"] for spec in schema]
    allowed = set(names)
    issues: list[dict[str, str]] = []

    def report(row: int, field: str, issue: str) -> None:
        if len(issues) < MAX_REPORTED_ISSUES:
            issues.append({"field": f"instances[{row}].{field}", "issue": issue})

    rows: list[list[Any]] = []
    for index, instance in enumerate(instances):
        for key in instance:
            if key not in allowed:
                report(index, str(key)[:64], "unknown field")
        values: list[Any] = []
        for spec in schema:
            name = spec["name"]
            if name not in instance:
                report(index, name, "required field is missing")
                values.append(None)
                continue
            problem = _value_issue(spec, instance[name])
            if problem:
                report(index, name, problem)
            values.append(instance[name])
        rows.append(values)

    if issues:
        raise InstanceValidationError(issues)

    frame = pd.DataFrame([[np.nan if v is None else v for v in row] for row in rows], columns=names)
    for spec in schema:
        if spec["kind"] == "numeric":
            frame[spec["name"]] = frame[spec["name"]].astype("float64")
    return frame


def jsonable_values(values: Any) -> list[Any]:
    """Convert numpy results to plain Python; non-finite numbers become `None`."""
    result = []
    for value in np.asarray(values).tolist():
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        result.append(value)
    return result
