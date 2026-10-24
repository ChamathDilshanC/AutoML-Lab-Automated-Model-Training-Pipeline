from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from automl.tasks import Task


class ExperimentStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset({ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED})


class RunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExperimentCreate(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    task: Task
    target_column: str = Field(min_length=1, max_length=255)
    metric: str | None = Field(default=None, max_length=32)  # defaults per task
    algorithms: list[str] = Field(min_length=1, max_length=10)
    random_seed: int = Field(default=42, ge=0, le=2**31 - 1)
    test_size: float = Field(default=0.2, ge=0.05, le=0.5)


class ExperimentResponse(BaseModel):
    experiment_id: str
    dataset_id: str
    task: Task
    target_column: str
    metric: str
    algorithms: list[str]
    random_seed: int
    test_size: float
    status: ExperimentStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_summary: str | None


class ExperimentRunResponse(BaseModel):
    run_id: str
    algorithm: str
    status: RunStatus
    hyperparameters: dict[str, Any]
    cv_score: float | None
    cv_folds: int | None
    metrics: dict[str, float | None]
    duration_seconds: float
    error_summary: str | None
    rank: int | None


class SelectionReason(BaseModel):
    metric: str
    direction: str  # "higher_is_better" or "lower_is_better"
    evaluated_on: str  # always the held-out test set
    tie_breaker: str


class LeaderboardResponse(BaseModel):
    experiment: ExperimentResponse
    metric: str
    higher_is_better: bool
    runs: list[ExperimentRunResponse]  # ranked runs first, then unranked, then failed
    selected_run_id: str | None
    selection_reason: SelectionReason | None
    split: dict[str, Any] | None
    library_versions: dict[str, str] | None


class MetricOption(BaseModel):
    name: str
    higher_is_better: bool


class TaskOptions(BaseModel):
    algorithms: list[str]
    metrics: list[MetricOption]
    default_metric: str


class ExperimentOptions(BaseModel):
    classification: TaskOptions
    regression: TaskOptions
