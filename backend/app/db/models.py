from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class Dataset(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    storage_key: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_summary: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    quality_warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    validation_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("ix_experiments_status_created", "status", "created_at"),
    )

    experiment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id"), index=True)
    target_column: Mapped[str] = mapped_column(String(255))
    task: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(32))
    algorithms: Mapped[list[str]] = mapped_column(JSON)
    random_seed: Mapped[int] = mapped_column(Integer)
    test_size: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selected_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    split_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    library_versions: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (UniqueConstraint("experiment_id", "algorithm"),)

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), index=True)
    algorithm: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cv_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cv_folds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics: Mapped[dict[str, float | None]] = mapped_column(JSON, default=dict)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RegisteredModel(Base):
    """An immutable, versioned model artifact produced by an experiment.

    `model_id` identifies one artifact. `version` counts the artifacts registered for the same
    owner, dataset, target column and task, so re-running an experiment yields version 2.
    """

    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("owner_id", "dataset_id", "target_column", "task", "version"),
    )

    model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[str] = mapped_column(String(128), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id"), index=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("experiment_runs.run_id"))
    task: Mapped[str] = mapped_column(String(32))
    target_column: Mapped[str] = mapped_column(String(255))
    algorithm: Mapped[str] = mapped_column(String(64))
    metric: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict[str, float | None]] = mapped_column(JSON)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    feature_schema: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    classes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    library_versions: Mapped[dict[str, str]] = mapped_column(JSON)
    artifact_key: Mapped[str] = mapped_column(String(512))
    metadata_key: Mapped[str] = mapped_column(String(512))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    artifact_bytes: Mapped[int] = mapped_column(Integer)
    approval_status: Mapped[str] = mapped_column(String(32))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    auth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AuditEvent(Base):
    """Who did what to which resource. Never holds passwords, tokens or dataset values."""

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16))  # "success" or "failure"
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
