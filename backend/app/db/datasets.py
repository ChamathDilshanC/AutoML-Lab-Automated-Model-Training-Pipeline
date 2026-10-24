"""Persistence for dataset metadata. Every lookup is scoped to the owner."""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Dataset, Experiment, ExperimentRun, RegisteredModel
from app.schemas.experiments import ExperimentStatus


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


def has_running_experiment(session: Session, dataset_id: str) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(Experiment)
        .where(Experiment.dataset_id == dataset_id, Experiment.status == ExperimentStatus.RUNNING)
    )
    return bool(count)


def delete_dataset_cascade(session: Session, dataset: Dataset) -> list[str]:
    """Delete a dataset and everything derived from it, in one transaction.

    Returns the IDs of the deleted models so their artifacts can be removed afterwards.
    """
    model_ids = list(
        session.scalars(
            select(RegisteredModel.model_id).where(RegisteredModel.dataset_id == dataset.dataset_id)
        )
    )
    experiment_ids = select(Experiment.experiment_id).where(
        Experiment.dataset_id == dataset.dataset_id
    )
    session.execute(delete(RegisteredModel).where(RegisteredModel.dataset_id == dataset.dataset_id))
    session.execute(delete(ExperimentRun).where(ExperimentRun.experiment_id.in_(experiment_ids)))
    session.execute(delete(Experiment).where(Experiment.dataset_id == dataset.dataset_id))
    session.execute(delete(Dataset).where(Dataset.dataset_id == dataset.dataset_id))
    session.commit()
    return model_ids
