from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DatasetStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"  # registered; the file is not validated yet
    UPLOADED = "UPLOADED"  # legacy: rows made before M6, whose file was stored at creation
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


class DatasetRegister(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class UploadTargetResponse(BaseModel):
    method: str
    url: str  # absolute for storage, or a path on this API when `requires_auth` is true
    headers: dict[str, str]  # send exactly these with the upload
    expires_in_seconds: int | None
    requires_auth: bool  # send the bearer token only when true; never to a presigned URL


class DatasetUploadResponse(DatasetResponse):
    upload: UploadTargetResponse
