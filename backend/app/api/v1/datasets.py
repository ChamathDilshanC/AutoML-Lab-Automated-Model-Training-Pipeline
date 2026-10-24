import tempfile
from typing import Annotated, BinaryIO, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_storage
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import get_owner_id
from app.db.audit import record_audit
from app.db.datasets import get_dataset
from app.db.models import Dataset
from app.db.session import get_session
from app.schemas.datasets import (
    DatasetRegister,
    DatasetResponse,
    DatasetStatus,
    DatasetUploadResponse,
    ValidationReport,
)
from app.services import datasets as dataset_service
from app.services.storage import StorageAdapter

router = APIRouter(prefix="/datasets", tags=["datasets"])

SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[StorageAdapter, Depends(get_storage)]
OwnerDep = Annotated[str, Depends(get_owner_id)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _owned_dataset(session: Session, owner_id: str, dataset_id: str) -> Dataset:
    dataset = get_dataset(session, owner_id, dataset_id)
    if dataset is None:  # also returned for other owners' datasets, so existence is not revealed
        raise ApiError(404, "NOT_FOUND", "Dataset not found.")
    return dataset


@router.post("", response_model=DatasetUploadResponse, status_code=201)
def register_dataset(
    payload: DatasetRegister,
    session: SessionDep,
    storage: StorageDep,
    owner_id: OwnerDep,
    settings: SettingsDep,
) -> DatasetUploadResponse:
    """Register a CSV and get a target to upload its bytes to.

    With S3 the target is a short-lived presigned URL (the browser uploads straight to storage);
    locally it is `PUT /api/v1/datasets/{id}/content` on this API. Either way the next step is
    `POST /api/v1/datasets/{id}/validate`.
    """
    dataset, target = dataset_service.register_dataset(
        session,
        storage,
        owner_id,
        payload.filename,
        payload.size_bytes,
        settings.max_upload_bytes,
    )
    return dataset_service.to_upload_response(dataset, target)


@router.put("/{dataset_id}/content", status_code=204)
async def upload_content(
    dataset_id: str,
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    owner_id: OwnerDep,
    settings: SettingsDep,
) -> Response:
    """Local-storage upload target. Not used when files go straight to S3."""
    dataset = _owned_dataset(session, owner_id, dataset_id)
    if settings.storage_mode != "local":
        raise ApiError(409, "STATE_CONFLICT", "Files are uploaded directly to storage.")
    if dataset.status != DatasetStatus.PENDING_UPLOAD:
        raise ApiError(409, "STATE_CONFLICT", "This dataset is not waiting for its file.")

    declared = dataset.size_bytes
    announced = request.headers.get("content-length", "")
    if announced.isdigit() and int(announced) > declared:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "The file is larger than its declared size.")

    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as spool:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > declared:
                raise ApiError(
                    413, "PAYLOAD_TOO_LARGE", "The file is larger than its declared size."
                )
            spool.write(chunk)
        spool.seek(0)
        await run_in_threadpool(
            dataset_service.store_content, storage, dataset, cast(BinaryIO, spool)
        )
    return Response(status_code=204)


@router.post("/{dataset_id}/validate", response_model=ValidationReport)
def validate_dataset(
    dataset_id: str,
    session: SessionDep,
    storage: StorageDep,
    owner_id: OwnerDep,
    settings: SettingsDep,
) -> ValidationReport:
    """Validate the uploaded file and return the data-quality report (`READY` or `REJECTED`)."""
    dataset = _owned_dataset(session, owner_id, dataset_id)
    dataset = dataset_service.validate_dataset(
        session, storage, dataset, max_bytes=settings.max_upload_bytes
    )
    report = dataset_service.to_report(dataset)
    assert report is not None  # a validated dataset is never waiting for its file
    return report


@router.get("/{dataset_id}", response_model=DatasetResponse)
def read_dataset(dataset_id: str, session: SessionDep, owner_id: OwnerDep) -> DatasetResponse:
    return dataset_service.to_response(_owned_dataset(session, owner_id, dataset_id))


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: str, session: SessionDep, storage: StorageDep, owner_id: OwnerDep
) -> Response:
    """Delete a dataset together with its experiments, runs, models and stored files."""
    dataset = _owned_dataset(session, owner_id, dataset_id)
    dataset_service.delete_dataset(session, storage, dataset)
    record_audit(
        session,
        "dataset.delete",
        actor_id=owner_id,
        resource_type="dataset",
        resource_id=dataset_id,
    )
    return Response(status_code=204)
