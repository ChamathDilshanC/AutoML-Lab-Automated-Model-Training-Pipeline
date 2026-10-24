from typing import Annotated

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_storage
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import get_owner_id
from app.db.audit import record_audit
from app.db.datasets import get_dataset
from app.db.models import Dataset
from app.db.session import get_session
from app.schemas.datasets import DatasetResponse, ValidationReport
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


@router.post("", response_model=DatasetResponse, status_code=201)
def upload_dataset(
    file: UploadFile,
    session: SessionDep,
    storage: StorageDep,
    owner_id: OwnerDep,
    settings: SettingsDep,
) -> DatasetResponse:
    """Upload a CSV file. The dataset is stored as `UPLOADED` until it is validated."""
    dataset = dataset_service.create_from_upload(
        session, storage, owner_id, file.filename, file.file, settings.max_upload_bytes
    )
    return dataset_service.to_response(dataset)


@router.post("/{dataset_id}/validate", response_model=ValidationReport)
def validate_dataset(
    dataset_id: str, session: SessionDep, storage: StorageDep, owner_id: OwnerDep
) -> ValidationReport:
    """Validate the uploaded file and return the data-quality report (`READY` or `REJECTED`)."""
    dataset = _owned_dataset(session, owner_id, dataset_id)
    dataset = dataset_service.validate_dataset(session, storage, dataset)
    report = dataset_service.to_report(dataset)
    assert report is not None  # a validated dataset is never UPLOADED
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
