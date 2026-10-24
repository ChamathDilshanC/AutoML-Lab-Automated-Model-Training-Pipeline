"""Persistence for dataset metadata. Every lookup is scoped to the owner."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dataset


def create_dataset(
    session: Session,
    *,
    dataset_id: str,
    owner_id: str,
    storage_key: str,
    original_filename: str,
    size_bytes: int,
    status: str,
) -> Dataset:
    dataset = Dataset(
        dataset_id=dataset_id,
        owner_id=owner_id,
        storage_key=storage_key,
        original_filename=original_filename,
        size_bytes=size_bytes,
        status=status,
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


def get_dataset(session: Session, owner_id: str, dataset_id: str) -> Dataset | None:
    return session.scalar(
        select(Dataset).where(Dataset.dataset_id == dataset_id, Dataset.owner_id == owner_id)
    )


def save_dataset(session: Session, dataset: Dataset) -> Dataset:
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset
