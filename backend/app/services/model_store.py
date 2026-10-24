"""Registering and loading model artifacts.

Used by the worker (registration) and the API (loading), so it imports no web-framework code.
Artifacts are written only here, and `load_pipeline` verifies the stored SHA-256 before it hands
the bytes to joblib (docs/ADR/0002).
"""

import io
import json
import logging
import uuid
from datetime import UTC
from typing import Any

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import registry as repo
from app.db.models import Experiment, ExperimentRun, RegisteredModel
from app.schemas.models import ApprovalStatus
from app.services.storage import StorageAdapter
from automl.registry import (
    build_feature_schema,
    build_metadata,
    dumps_pipeline,
    loads_pipeline,
    sha256_hex,
)
from automl.trainer import TrainedModel

logger = logging.getLogger(__name__)


class ArtifactIntegrityError(Exception):
    """The stored artifact is missing or does not match its recorded checksum."""


def artifact_keys(model_id: str, version: int) -> tuple[str, str]:
    prefix = f"models/{model_id}/{version}"
    return f"{prefix}/model.joblib", f"{prefix}/metadata.json"


def register_model(
    session: Session,
    storage: StorageAdapter,
    *,
    experiment: Experiment,
    run: ExperimentRun,
    trained: TrainedModel,
    X_train: pd.DataFrame,
    split_info: dict[str, Any],
    max_artifact_bytes: int,
) -> RegisteredModel:
    """Save the winning pipeline and its metadata, then record it as `PENDING` approval.

    On any failure the files written so far are removed, so no orphaned artifact is left.
    """
    feature_schema = build_feature_schema(X_train)
    artifact = dumps_pipeline(trained.pipeline)
    digest = sha256_hex(artifact)

    for attempt in range(2):
        version = repo.next_version(
            session,
            experiment.owner_id,
            experiment.dataset_id,
            experiment.target_column,
            experiment.task,
        )
        model_id = f"md_{uuid.uuid4().hex}"
        artifact_key, metadata_key = artifact_keys(model_id, version)
        created_at = utc_now()
        metadata = build_metadata(
            model_id=model_id,
            version=version,
            experiment_id=experiment.experiment_id,
            run_id=run.run_id,
            trained=trained,
            metric=experiment.metric,
            metrics=run.metrics,
            feature_schema=feature_schema,
            split_info=split_info,
            target_column=experiment.target_column,
            created_at=created_at.replace(tzinfo=UTC).isoformat(),
        )
        try:
            storage.save(artifact_key, io.BytesIO(artifact), max_artifact_bytes)
            storage.save(
                metadata_key,
                io.BytesIO(json.dumps(metadata, indent=2, default=str).encode()),
                max_artifact_bytes,
            )
            return repo.create_model(
                session,
                model_id=model_id,
                version=version,
                owner_id=experiment.owner_id,
                dataset_id=experiment.dataset_id,
                experiment_id=experiment.experiment_id,
                run_id=run.run_id,
                task=experiment.task,
                target_column=experiment.target_column,
                algorithm=run.algorithm,
                metric=experiment.metric,
                metrics=run.metrics,
                hyperparameters=run.hyperparameters,
                feature_schema=feature_schema,
                classes=metadata["classes"],
                library_versions=trained.library_versions,
                artifact_key=artifact_key,
                metadata_key=metadata_key,
                artifact_sha256=digest,
                artifact_bytes=len(artifact),
                approval_status=ApprovalStatus.PENDING,
                created_at=created_at,
            )
        except IntegrityError:
            # Another worker took this version number: clean up and try once more.
            session.rollback()
            storage.delete(artifact_key)
            storage.delete(metadata_key)
            if attempt == 1:
                raise
        except BaseException:
            session.rollback()
            storage.delete(artifact_key)
            storage.delete(metadata_key)
            raise
    raise AssertionError("unreachable")  # pragma: no cover


def load_pipeline(storage: StorageAdapter, model: RegisteredModel) -> Any:
    """Read a registered artifact, verify its checksum, and only then deserialise it."""
    try:
        data = storage.read(model.artifact_key)
    except FileNotFoundError:
        raise ArtifactIntegrityError("artifact is missing") from None
    if sha256_hex(data) != model.artifact_sha256:
        logger.error("Checksum mismatch for model %s", model.model_id)
        raise ArtifactIntegrityError("artifact checksum mismatch")
    return loads_pipeline(data)
