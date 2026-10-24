"""Model queries and prediction serving (API side)."""

import logging
import threading
import time
from collections import OrderedDict
from typing import Any

import sklearn
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.time import as_utc
from app.db.models import Dataset, RegisteredModel
from app.schemas.models import (
    ApprovalStatus,
    FeatureSpec,
    ModelResponse,
    PredictionResponse,
)
from app.services.model_store import ArtifactIntegrityError, load_pipeline
from app.services.storage import StorageAdapter
from automl.registry import InstanceValidationError, instances_to_frame, jsonable_values

logger = logging.getLogger(__name__)

# Registered artifacts never change, so a loaded pipeline can be reused. The size bounds memory.
_CACHE_SIZE = 4
_cache: OrderedDict[str, Any] = OrderedDict()
_cache_lock = threading.Lock()


def clear_model_cache() -> None:
    with _cache_lock:
        _cache.clear()


def filenames_for(session: Session, models: list[RegisteredModel]) -> dict[str, str]:
    ids = {model.dataset_id for model in models}
    if not ids:
        return {}
    rows = session.execute(
        select(Dataset.dataset_id, Dataset.original_filename).where(Dataset.dataset_id.in_(ids))
    )
    return {dataset_id: filename for dataset_id, filename in rows}


def to_response(model: RegisteredModel, dataset_filename: str | None) -> ModelResponse:
    return ModelResponse(
        model_id=model.model_id,
        version=model.version,
        dataset_id=model.dataset_id,
        dataset_filename=dataset_filename,
        experiment_id=model.experiment_id,
        run_id=model.run_id,
        task=model.task,  # type: ignore[arg-type]  # validated when the experiment was queued
        target_column=model.target_column,
        algorithm=model.algorithm,
        metric=model.metric,
        metrics=model.metrics,
        hyperparameters=model.hyperparameters,
        feature_schema=[FeatureSpec(**spec) for spec in model.feature_schema],
        classes=model.classes,
        library_versions=model.library_versions,
        artifact_bytes=model.artifact_bytes,
        approval_status=ApprovalStatus(model.approval_status),
        approved_at=as_utc(model.approved_at) if model.approved_at else None,
        created_at=as_utc(model.created_at),
    )


def _get_pipeline(storage: StorageAdapter, model: RegisteredModel) -> Any:
    with _cache_lock:
        if model.model_id in _cache:
            _cache.move_to_end(model.model_id)
            return _cache[model.model_id]
    try:
        pipeline = load_pipeline(storage, model)
    except ArtifactIntegrityError:
        raise ApiError(
            500,
            "INTERNAL_ERROR",
            "The model artifact is unavailable or failed its integrity check.",
        ) from None
    with _cache_lock:
        _cache[model.model_id] = pipeline
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return pipeline


def predict(
    storage: StorageAdapter,
    model: RegisteredModel,
    instances: list[dict[str, Any]],
    *,
    max_batch: int,
    request_id: str | None,
) -> PredictionResponse:
    """Validate the input against the model's schema, then run the approved model."""
    if model.approval_status != ApprovalStatus.APPROVED:
        raise ApiError(409, "STATE_CONFLICT", "The model is not approved for predictions.")
    if len(instances) > max_batch:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Too many instances; the limit is {max_batch}.",
            [{"field": "instances", "issue": f"at most {max_batch} allowed"}],
        )
    trained_with = model.library_versions.get("scikit-learn")
    if trained_with != sklearn.__version__:
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "This model was trained with a different scikit-learn version "
            "and cannot be used safely.",
        )

    # Input is plain JSON, checked field by field. It is never passed to joblib or pickle.
    try:
        frame = instances_to_frame(model.feature_schema, instances)
    except InstanceValidationError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc), exc.issues) from None

    started = time.perf_counter()
    pipeline = _get_pipeline(storage, model)
    predictions = jsonable_values(pipeline.predict(frame))
    probabilities = None
    classes = None
    if model.task == "classification" and hasattr(pipeline, "predict_proba"):
        classes = [c for c in model.classes or []]
        probabilities = [
            {str(label): round(float(p), 6) for label, p in zip(classes, row, strict=True)}
            for row in pipeline.predict_proba(frame)
        ]

    # Which version served the request; never the input values.
    logger.info(
        "prediction model=%s version=%s rows=%d ms=%.1f request=%s",
        model.model_id,
        model.version,
        len(instances),
        (time.perf_counter() - started) * 1000,
        request_id,
    )
    return PredictionResponse(
        model_id=model.model_id,
        model_version=model.version,
        predictions=predictions,
        classes=classes,
        probabilities=probabilities,
        request_id=request_id,
    )
