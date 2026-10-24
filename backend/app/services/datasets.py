"""Dataset upload and validation workflow."""

import os
import re
import uuid
from dataclasses import asdict
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.time import as_utc
from app.db.datasets import create_dataset, save_dataset
from app.db.models import Dataset
from app.schemas.datasets import (
    ColumnSummary,
    DatasetResponse,
    DatasetStatus,
    QualityWarning,
    ValidationReport,
)
from app.services.storage import FileTooLargeError, StorageAdapter
from automl.quality import quality_warnings, summarize_schema
from automl.validation import DataValidationError, ValidationLimits, read_csv_bytes

MAX_FILENAME_LENGTH = 255
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: str | None) -> str:
    """Reduce a client-supplied name to a safe display name. It is never used as a storage path."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = _CONTROL_CHARACTERS.sub("", base).strip()
    return base[:MAX_FILENAME_LENGTH] or "upload.csv"


def storage_key(owner_id: str, dataset_id: str) -> str:
    return f"datasets/{owner_id}/{dataset_id}/source.csv"


def create_from_upload(
    session: Session,
    storage: StorageAdapter,
    owner_id: str,
    filename: str | None,
    stream: BinaryIO,
    max_bytes: int,
) -> Dataset:
    """Store an uploaded file and register it as `UPLOADED`."""
    display_name = sanitize_filename(filename)
    if not display_name.lower().endswith(".csv"):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Only .csv files are supported.",
            [{"field": "file", "issue": "unsupported_file_type"}],
        )

    dataset_id = f"ds_{uuid.uuid4().hex}"
    key = storage_key(owner_id, dataset_id)
    try:
        size = storage.save(key, stream, max_bytes)
    except FileTooLargeError:
        raise ApiError(
            413, "PAYLOAD_TOO_LARGE", f"File is larger than the {max_bytes} byte limit."
        ) from None

    try:
        return create_dataset(
            session,
            dataset_id=dataset_id,
            owner_id=owner_id,
            storage_key=key,
            original_filename=display_name,
            size_bytes=size,
            status=DatasetStatus.UPLOADED,
        )
    except Exception:
        storage.delete(key)
        raise


def validate_dataset(
    session: Session,
    storage: StorageAdapter,
    dataset: Dataset,
    limits: ValidationLimits | None = None,
) -> Dataset:
    """Validate the stored file and record `READY` or `REJECTED`.

    Validating a dataset that was already decided returns it unchanged. A rejected dataset's
    file is removed from storage.
    """
    if dataset.status != DatasetStatus.UPLOADED:
        return dataset

    try:
        data = storage.read(dataset.storage_key)
    except FileNotFoundError:
        raise ApiError(409, "STATE_CONFLICT", "The uploaded file is no longer available.") from None

    try:
        df = read_csv_bytes(data, limits)
    except DataValidationError as exc:
        dataset.status = DatasetStatus.REJECTED
        dataset.validation_message = str(exc)[:500]
        storage.delete(dataset.storage_key)
    else:
        dataset.status = DatasetStatus.READY
        dataset.row_count = len(df)
        dataset.column_count = len(df.columns)
        dataset.schema_summary = [asdict(column) for column in summarize_schema(df)]
        dataset.quality_warnings = [asdict(warning) for warning in quality_warnings(df)]
    return save_dataset(session, dataset)


def to_report(dataset: Dataset) -> ValidationReport | None:
    if dataset.status == DatasetStatus.UPLOADED:
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
