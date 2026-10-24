from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import get_owner_id
from app.db import experiments as repo
from app.db import registry as model_repo
from app.db.datasets import get_dataset
from app.db.models import Experiment
from app.db.session import get_session
from app.schemas.experiments import (
    TERMINAL_STATUSES,
    ExperimentCreate,
    ExperimentOptions,
    ExperimentResponse,
    LeaderboardResponse,
)
from app.services import experiments as experiment_service

router = APIRouter(prefix="/experiments", tags=["experiments"])

SessionDep = Annotated[Session, Depends(get_session)]
OwnerDep = Annotated[str, Depends(get_owner_id)]


def _owned_experiment(session: Session, owner_id: str, experiment_id: str) -> Experiment:
    experiment = repo.get_experiment(session, owner_id, experiment_id)
    if experiment is None:  # also returned for other owners' experiments
        raise ApiError(404, "NOT_FOUND", "Experiment not found.")
    return experiment


# Declared before the `{experiment_id}` routes so "options" is not read as an ID.
@router.get("/options", response_model=ExperimentOptions)
def experiment_options() -> ExperimentOptions:
    """Tasks, allowlisted algorithms and metrics (with direction) that experiments can use."""
    return experiment_service.get_options()


@router.post("", response_model=ExperimentResponse, status_code=202)
def create_experiment(
    payload: ExperimentCreate,
    session: SessionDep,
    owner_id: OwnerDep,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> ExperimentResponse:
    """Queue an experiment for the worker. Training does not happen in this request."""
    dataset = get_dataset(session, owner_id, payload.dataset_id)
    if dataset is None:
        raise ApiError(404, "NOT_FOUND", "Dataset not found.")
    experiment = experiment_service.create_experiment(
        session, owner_id, dataset, payload, idempotency_key
    )
    return experiment_service.to_response(experiment)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def read_experiment(
    experiment_id: str, session: SessionDep, owner_id: OwnerDep
) -> ExperimentResponse:
    return experiment_service.to_response(_owned_experiment(session, owner_id, experiment_id))


@router.get("/{experiment_id}/results", response_model=LeaderboardResponse)
def read_results(
    experiment_id: str, session: SessionDep, owner_id: OwnerDep
) -> LeaderboardResponse:
    """The ranked runs, available once the experiment has finished."""
    experiment = _owned_experiment(session, owner_id, experiment_id)
    if experiment.status not in TERMINAL_STATUSES:
        raise ApiError(409, "STATE_CONFLICT", "The experiment has not finished yet.")
    runs = repo.list_runs(session, experiment.experiment_id)
    model = model_repo.get_model_for_experiment(session, experiment.experiment_id)
    return experiment_service.build_leaderboard(experiment, runs, model.model_id if model else None)
