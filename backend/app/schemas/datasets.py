from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class DatasetStatus(StrEnum):
    UPLOADED = "UPLOADED"  # stored, not yet validated
    READY = "READY"
    REJECTED = "REJECTED"


class ColumnSummary(BaseModel):
    name: str
    kind: str
    missing_count: int
    missing_percent: float
    unique_count: int


class QualityWarning(BaseModel):
    code: str
    severity: str
    message: str
    columns: list[str]


class ValidationReport(BaseModel):
    status: DatasetStatus
    row_count: int | None
    column_count: int | None
    columns: list[ColumnSummary]
    warnings: list[QualityWarning]
    message: str | None


class DatasetResponse(BaseModel):
    dataset_id: str
    original_filename: str
    size_bytes: int
    status: DatasetStatus
    created_at: datetime
    validation: ValidationReport | None
