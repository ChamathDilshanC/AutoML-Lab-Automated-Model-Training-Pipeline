from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from automl.tasks import Task


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"


class FeatureSpec(BaseModel):
    name: str
    kind: Literal["numeric", "categorical"]
    value_type: Literal["number", "string", "boolean"]
    categories: list[str] | None


class ModelResponse(BaseModel):
    model_id: str
    version: int
    dataset_id: str
    dataset_filename: str | None
    experiment_id: str
    run_id: str
    task: Task
    target_column: str
    algorithm: str
    metric: str
    metrics: dict[str, float | None]
    hyperparameters: dict[str, Any]
    feature_schema: list[FeatureSpec]
    classes: list[Any] | None
    library_versions: dict[str, str]
    artifact_bytes: int
    approval_status: ApprovalStatus
    approved_at: datetime | None
    created_at: datetime


class ModelApproveRequest(BaseModel):
    """Approval makes a model available for predictions, so it must be explicit."""

    confirm: Literal[True]


class PredictionRequest(BaseModel):
    # One object per row, keyed by feature name. Validated against the model's feature schema.
    instances: list[dict[str, Any]] = Field(min_length=1)


class PredictionResponse(BaseModel):
    model_id: str
    model_version: int
    predictions: list[Any]
    classes: list[Any] | None
    probabilities: list[dict[str, float]] | None  # classification only, keyed by class label
    request_id: str | None
