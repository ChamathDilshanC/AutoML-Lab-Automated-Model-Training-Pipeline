from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
