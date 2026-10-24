"""Persistence for experiments and runs.

Used by both the API and the worker process, so it must not import web-framework code.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.db.models import Experiment, ExperimentRun
from app.schemas.experiments import ExperimentStatus

STALE_MESSAGE = "The worker stopped before the experiment finished."


def create_experiment(session: Session, **fields: Any) -> Experiment:
    """Insert an experiment. Raises `IntegrityError` on a duplicate idempotency key."""
    experiment = Experiment(**fields)
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def get_experiment(session: Session, owner_id: str, experiment_id: str) -> Experiment | None:
    return session.scalar(
        select(Experiment).where(
            Experiment.experiment_id == experiment_id, Experiment.owner_id == owner_id
        )
    )


def find_by_idempotency_key(session: Session, owner_id: str, key: str) -> Experiment | None:
    return session.scalar(
        select(Experiment).where(Experiment.owner_id == owner_id, Experiment.idempotency_key == key)
    )


def list_runs(session: Session, experiment_id: str) -> list[ExperimentRun]:
    return list(
        session.scalars(
            select(ExperimentRun)
            .where(ExperimentRun.experiment_id == experiment_id)
            .order_by(ExperimentRun.created_at, ExperimentRun.algorithm)
        )
    )


def add_run(session: Session, **fields: Any) -> ExperimentRun:
    run = ExperimentRun(**fields)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def claim_experiment(session: Session, experiment_id: str) -> Experiment | None:
    """Atomically move one `QUEUED` experiment to `RUNNING` and return it.

    Returns `None` if it is not queued any more (already claimed, finished, reaped or deleted).
    The conditional UPDATE means that when several workers, or several deliveries of the same
    queue message, race for a job, exactly one wins.
    """
    result = session.execute(
        update(Experiment)
        .where(
            Experiment.experiment_id == experiment_id,
            Experiment.status == ExperimentStatus.QUEUED,
        )
        .values(status=ExperimentStatus.RUNNING, started_at=utc_now())
    )
    session.commit()
    assert isinstance(result, CursorResult)
    if result.rowcount != 1:
        return None
    experiment = session.get(Experiment, experiment_id)
    if experiment is not None:
        session.refresh(experiment)
    return experiment


def claim_next_queued(session: Session) -> Experiment | None:
    """Claim the oldest `QUEUED` experiment (the database is the queue in `db` job mode)."""
    for _ in range(3):
        candidate = session.scalar(
            select(Experiment.experiment_id)
            .where(Experiment.status == ExperimentStatus.QUEUED)
            .order_by(Experiment.created_at, Experiment.experiment_id)
            .limit(1)
        )
        if candidate is None:
            return None
        experiment = claim_experiment(session, candidate)
        if experiment is not None:
            return experiment
    return None


def delete_experiment(session: Session, experiment_id: str) -> None:
    """Remove an experiment that never started (used to undo a failed queue hand-off)."""
    session.execute(delete(Experiment).where(Experiment.experiment_id == experiment_id))
    session.commit()


def finish_experiment(
    session: Session,
    experiment: Experiment,
    *,
    status: ExperimentStatus,
    error_summary: str | None = None,
    selected_run_id: str | None = None,
    split_info: dict[str, Any] | None = None,
    library_versions: dict[str, str] | None = None,
) -> Experiment:
    """Record the outcome, but only if the experiment is still `RUNNING`.

    If something else already ended it (for example the stale-job reaper), that outcome stands
    and this call changes nothing. The returned experiment reflects what is in the database.
    """
    session.execute(
        update(Experiment)
        .where(
            Experiment.experiment_id == experiment.experiment_id,
            Experiment.status == ExperimentStatus.RUNNING,
        )
        .values(
            status=status,
            finished_at=utc_now(),
            error_summary=error_summary[:500] if error_summary else None,
            selected_run_id=selected_run_id,
            split_info=split_info,
            library_versions=library_versions,
        )
    )
    session.commit()
    session.refresh(experiment)
    return experiment


def fail_stale_experiments(
    session: Session, timeout_seconds: int, now: datetime | None = None
) -> int:
    """Mark `RUNNING` experiments that started too long ago as `FAILED`. Returns the count."""
    now = now or utc_now()
    cutoff = now - timedelta(seconds=timeout_seconds)
    result = session.execute(
        update(Experiment)
        .where(Experiment.status == ExperimentStatus.RUNNING, Experiment.started_at < cutoff)
        .values(status=ExperimentStatus.FAILED, finished_at=now, error_summary=STALE_MESSAGE)
    )
    session.commit()
    assert isinstance(result, CursorResult)
    return int(result.rowcount)


def reap_stale(session_factory: sessionmaker[Session], timeout_seconds: int) -> int:
    """Fail `RUNNING` experiments older than the timeout, using a fresh session."""
    with session_factory() as session:
        return fail_stale_experiments(session, timeout_seconds)
