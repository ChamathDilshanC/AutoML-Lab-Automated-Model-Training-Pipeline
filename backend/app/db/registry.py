"""Persistence for registered models. Used by the API and the worker (no web-framework imports)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models import RegisteredModel
from app.schemas.models import ApprovalStatus


def next_version(
    session: Session, owner_id: str, dataset_id: str, target_column: str, task: str
) -> int:
    latest = session.scalar(
        select(func.max(RegisteredModel.version)).where(
            RegisteredModel.owner_id == owner_id,
            RegisteredModel.dataset_id == dataset_id,
            RegisteredModel.target_column == target_column,
            RegisteredModel.task == task,
        )
    )
    return int(latest or 0) + 1


def create_model(session: Session, **fields: Any) -> RegisteredModel:
    """Insert a model. Raises `IntegrityError` if the version number was taken concurrently."""
    model = RegisteredModel(**fields)
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def get_model(session: Session, owner_id: str, model_id: str) -> RegisteredModel | None:
    return session.scalar(
        select(RegisteredModel).where(
            RegisteredModel.model_id == model_id, RegisteredModel.owner_id == owner_id
        )
    )


def list_models(session: Session, owner_id: str) -> list[RegisteredModel]:
    return list(
        session.scalars(
            select(RegisteredModel)
            .where(RegisteredModel.owner_id == owner_id)
            .order_by(RegisteredModel.created_at.desc(), RegisteredModel.model_id)
        )
    )


def get_model_for_experiment(session: Session, experiment_id: str) -> RegisteredModel | None:
    return session.scalar(
        select(RegisteredModel).where(RegisteredModel.experiment_id == experiment_id)
    )


def approve_model(session: Session, model: RegisteredModel) -> RegisteredModel:
    """Mark a model approved. Approving an approved model changes nothing."""
    if model.approval_status != ApprovalStatus.APPROVED:
        model.approval_status = ApprovalStatus.APPROVED
        model.approved_at = utc_now()
        session.add(model)
        session.commit()
        session.refresh(model)
    return model
