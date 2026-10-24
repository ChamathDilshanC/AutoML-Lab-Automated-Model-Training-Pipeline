"""Dataset upload and validation workflow."""

import logging
import os
import re
import uuid
from dataclasses import asdict
from pathlib import PurePosixPath
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.time import as_utc
from app.db.datasets import (
    create_dataset,
    delete_dataset_cascade,
    has_running_experiment,
    save_dataset,
)
from app.db.models import Dataset
from app.schemas.datasets import (
    ColumnSummary,
    DatasetResponse,
    DatasetStatus,
    DatasetUploadResponse,
    QualityWarning,
    UploadTargetResponse,
    ValidationReport,
)
from app.services.models import evict_models
from app.services.storage import FileTooLargeError, StorageAdapter, UploadTarget
from automl.quality import quality_warnings, summarize_schema
from automl.validation import DataValidationError, ValidationLimits, read_csv_bytes

logger = logging.getLogger(__name__)

MAX_FILENAME_LENGTH = 255
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: str | None) -> str:
    """Reduce a client-supplied name to a safe display name. It is never used as a storage path."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = _CONTROL_CHARACTERS.sub("", base).strip()
    return base[:MAX_FILENAME_LENGTH] or "upload.csv"


def storage_key(owner_id: str, dataset_id: str) -> str:
    return f"datasets/{owner_id}/{dataset_id}/source.csv"


CSV_CONTENT_TYPE = "text/csv"
# `UPLOADED` rows were created before M6 with their file already stored.
AWAITING_VALIDATION = (DatasetStatus.PENDING_UPLOAD, DatasetStatus.UPLOADED)


def register_dataset(
    session: Session,
    storage: StorageAdapter,
    owner_id: str,
    filename: str,
    size_bytes: int,
    max_bytes: int,
) -> tuple[Dataset, UploadTarget | None]:
    """Create the record and the upload target. The file itself arrives separately.

    The declared size is the contract: it is checked against the limit here, signed into a
    presigned URL (S3 refuses any other length), enforced on the local upload endpoint, and
    compared with what is really stored when the file is validated.
    """
    display_name = sanitize_filename(filename)
    if not display_name.lower().endswith(".csv"):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Only .csv files are supported.",
            [{"field": "filename", "issue": "unsupported_file_type"}],
        )
    if size_bytes > max_bytes:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", f"File is larger than the {max_bytes} byte limit.")

    dataset_id = f"ds_{uuid.uuid4().hex}"
    key = storage_key(owner_id, dataset_id)
    target = storage.upload_target(key, size_bytes, CSV_CONTENT_TYPE)
    dataset = create_dataset(
        session,
        dataset_id=dataset_id,
        owner_id=owner_id,
        storage_key=key,
        original_filename=display_name,
        size_bytes=size_bytes,
        status=DatasetStatus.PENDING_UPLOAD,
    )
    return dataset, target


def store_content(storage: StorageAdapter, dataset: Dataset, stream: BinaryIO) -> None:
    """Save an upload that came through this API (local storage mode)."""
    try:
        written = storage.save(dataset.storage_key, stream, dataset.size_bytes)
    except FileTooLargeError:
        raise ApiError(
            413, "PAYLOAD_TOO_LARGE", "The file is larger than its declared size."
        ) from None
    if written != dataset.size_bytes:
        storage.delete(dataset.storage_key)
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "The uploaded size does not match the declared size.",
            [{"field": "body", "issue": "size_mismatch"}],
        )


def validate_dataset(
    session: Session,
    storage: StorageAdapter,
    dataset: Dataset,
    limits: ValidationLimits | None = None,
    max_bytes: int | None = None,
) -> Dataset:
    """Validate the stored file and record `READY` or `REJECTED`.

    Validating a dataset that was already decided returns it unchanged. A rejected dataset's
    file is removed from storage. If no file has arrived yet that is a conflict, not a rejection,
    so the client can upload and try again.
    """
    if dataset.status not in AWAITING_VALIDATION:
        return dataset

    try:
        actual = storage.size(dataset.storage_key)
    except FileNotFoundError:
        raise ApiError(
            409, "STATE_CONFLICT", "No file has been uploaded for this dataset yet."
        ) from None

    if actual != dataset.size_bytes or (max_bytes is not None and actual > max_bytes):
        return _reject(
            session, storage, dataset, "The uploaded file does not match its declared size."
        )

    try:
        df = read_csv_bytes(storage.read(dataset.storage_key), limits)
    except DataValidationError as exc:
        return _reject(session, storage, dataset, str(exc))
    dataset.status = DatasetStatus.READY
    dataset.row_count = len(df)
    dataset.column_count = len(df.columns)
    dataset.schema_summary = [asdict(column) for column in summarize_schema(df)]
    dataset.quality_warnings = [asdict(warning) for warning in quality_warnings(df)]
    return save_dataset(session, dataset)


def _reject(session: Session, storage: StorageAdapter, dataset: Dataset, message: str) -> Dataset:
    dataset.status = DatasetStatus.REJECTED
    dataset.validation_message = message[:500]
    storage.delete(dataset.storage_key)
    return save_dataset(session, dataset)


def delete_dataset(session: Session, storage: StorageAdapter, dataset: Dataset) -> None:
    """Delete a dataset, its experiments, runs and models, and every stored file.

    Refused while one of its experiments is running, because the worker is using the files.
    Database rows go first, in one transaction; files are removed afterwards, so a failure there
    leaves unreachable files, never a record pointing at missing ones.
    """
    if has_running_experiment(session, dataset.dataset_id):
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "An experiment on this dataset is running. Delete it after the experiment finishes.",
        )
    dataset_folder = str(PurePosixPath(dataset.storage_key).parent)
    model_ids = delete_dataset_cascade(session, dataset)
    evict_models(model_ids)
    for prefix in [dataset_folder, *(f"models/{model_id}" for model_id in model_ids)]:
        try:
            storage.delete_prefix(prefix)
        except Exception:
            logger.exception("Could not remove stored files under %s", prefix)


def to_report(dataset: Dataset) -> ValidationReport | None:
    if dataset.status in AWAITING_VALIDATION:
        return None
    return ValidationReport(
        status=DatasetStatus(dataset.status),
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        columns=[ColumnSummary(**column) for column in dataset.schema_summary or []],
        warnings=[QualityWarning(**warning) for warning in dataset.quality_warnings or []],
        message=dataset.validation_message,
    )


def to_response(dataset: Dataset) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=dataset.dataset_id,
        original_filename=dataset.original_filename,
        size_bytes=dataset.size_bytes,
        status=DatasetStatus(dataset.status),
        created_at=as_utc(dataset.created_at),
        validation=to_report(dataset),
    )


def to_upload_response(dataset: Dataset, target: UploadTarget | None) -> DatasetUploadResponse:
    """The registered dataset plus where to send its bytes."""
    if target is None:  # local mode: the file goes to this API
        target = UploadTarget(
            method="PUT",
            url=f"/api/v1/datasets/{dataset.dataset_id}/content",
            headers={"Content-Type": CSV_CONTENT_TYPE},
            expires_in_seconds=None,
            requires_auth=True,
        )
    return DatasetUploadResponse(
        **to_response(dataset).model_dump(),
        upload=UploadTargetResponse(
            method=target.method,
            url=target.url,
            headers=target.headers,
            expires_in_seconds=target.expires_in_seconds,
            requires_auth=target.requires_auth,
        ),
    )
