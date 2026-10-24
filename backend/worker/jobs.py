"""Experiment execution.

This runs in the worker process, never inside a web request, and must not import web-framework
code (a test enforces that). Failures are recorded on the experiment and never escape to the
worker loop.
"""

import json
import logging
import math
import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.db import experiments as repo
from app.db.models import Dataset, Experiment, ExperimentRun
from app.schemas.datasets import DatasetStatus
from app.schemas.experiments import ExperimentStatus, RunStatus
from app.services.model_store import register_model
from app.services.storage import StorageAdapter
from automl.evaluator import evaluate, rank_results
from automl.splits import separate_target, split_data
from automl.tasks import Task
from automl.trainer import TrainedModel, library_versions, train_model
from automl.validation import DataValidationError, read_csv_bytes, validate_target

logger = logging.getLogger("worker")

UNEXPECTED_FAILURE = "Unexpected error while running the experiment."
RUN_FAILURE = "Training failed for this algorithm."
NO_RESULT = "No algorithm produced a usable result."
DATASET_UNAVAILABLE = "The dataset is no longer available."
MODEL_NOT_SAVED = "The winning model could not be saved."
STOPPED_EARLY = "The experiment was stopped before it finished."
DEFAULT_MAX_ARTIFACT_BYTES = 200 * 1024 * 1024


class JobFailure(Exception):
    """A failure whose message is safe to show to the user."""


def _finite(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None


def _clean_metrics(metrics: dict[str, float | None]) -> dict[str, float | None]:
    """JSON cannot represent NaN or infinity, so those become `None`."""
    return {name: _finite(value) for name, value in metrics.items()}


def _jsonable(value: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(value, default=str))
    assert isinstance(result, dict)
    return result


def run_experiment(
    session: Session,
    storage: StorageAdapter,
    experiment: Experiment,
    *,
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
) -> None:
    """Load the dataset, train and evaluate each algorithm, and record the outcome.

    The winning pipeline is saved before the experiment is marked `SUCCEEDED`, so a succeeded
    experiment always has a registered model. The other pipelines are discarded.
    """
    dataset = session.get(Dataset, experiment.dataset_id)
    if dataset is None or dataset.status != DatasetStatus.READY:
        raise JobFailure(DATASET_UNAVAILABLE)
    try:
        data = storage.read(dataset.storage_key)
    except FileNotFoundError:
        raise JobFailure(DATASET_UNAVAILABLE) from None

    task: Task = experiment.task  # type: ignore[assignment]  # validated when it was queued
    try:
        df = read_csv_bytes(data)
        validate_target(df, experiment.target_column, task)
        X, y = separate_target(df, experiment.target_column)
        split = split_data(
            X, y, task, test_size=experiment.test_size, random_state=experiment.random_seed
        )
    except DataValidationError as exc:
        raise JobFailure(str(exc)) from None

    runs: dict[str, ExperimentRun] = {}
    fitted: dict[str, TrainedModel] = {}
    metrics_by_algorithm: dict[str, dict[str, float | None]] = {}
    versions: dict[str, str] | None = None

    for algorithm in experiment.algorithms:
        started = time.perf_counter()
        try:
            model = train_model(
                split.X_train,
                split.y_train,
                task,
                algorithm,
                metric=experiment.metric,
                random_state=experiment.random_seed,
            )
            metrics = _clean_metrics(evaluate(model.pipeline, split.X_test, split.y_test, task))
        except Exception:
            # Logged in full for the operator; the user only sees a generic message because
            # library errors can quote data.
            logger.exception(
                "Run failed: experiment=%s algorithm=%s", experiment.experiment_id, algorithm
            )
            repo.add_run(
                session,
                run_id=f"rn_{uuid.uuid4().hex}",
                experiment_id=experiment.experiment_id,
                algorithm=algorithm,
                status=RunStatus.FAILED,
                error_summary=RUN_FAILURE,
                duration_seconds=round(time.perf_counter() - started, 3),
            )
            continue

        versions = model.library_versions
        fitted[algorithm] = model
        metrics_by_algorithm[algorithm] = metrics
        runs[algorithm] = repo.add_run(
            session,
            run_id=f"rn_{uuid.uuid4().hex}",
            experiment_id=experiment.experiment_id,
            algorithm=algorithm,
            status=RunStatus.SUCCEEDED,
            hyperparameters=_jsonable(model.best_params),
            cv_score=_finite(model.cv_score),
            cv_folds=model.cv_folds,
            metrics=metrics,
            duration_seconds=round(time.perf_counter() - started, 3),
        )

    ranking = rank_results(metrics_by_algorithm, task, experiment.metric)
    for position, algorithm in enumerate(ranking, start=1):
        runs[algorithm].rank = position
        session.add(runs[algorithm])
    session.commit()

    if not ranking:
        repo.finish_experiment(
            session, experiment, status=ExperimentStatus.FAILED, error_summary=NO_RESULT
        )
        return
    split_info = {
        "strategy": split.strategy,
        "test_size": split.test_size,
        "random_state": split.random_state,
        "n_train": len(split.X_train),
        "n_test": len(split.X_test),
    }
    winner = ranking[0]
    session.refresh(experiment)
    if experiment.status != ExperimentStatus.RUNNING:
        # Ended by something else while training (for example the stale-job reaper).
        raise JobFailure(STOPPED_EARLY)
    try:
        register_model(
            session,
            storage,
            experiment=experiment,
            run=runs[winner],
            trained=fitted[winner],
            X_train=split.X_train,
            split_info=split_info,
            max_artifact_bytes=max_artifact_bytes,
        )
    except Exception:
        logger.exception("Could not save the model for experiment %s", experiment.experiment_id)
        raise JobFailure(MODEL_NOT_SAVED) from None

    repo.finish_experiment(
        session,
        experiment,
        status=ExperimentStatus.SUCCEEDED,
        selected_run_id=runs[winner].run_id,
        split_info=split_info,
        library_versions=versions or library_versions(),
    )


def _fail(session: Session, experiment: Experiment, message: str) -> None:
    session.rollback()
    repo.finish_experiment(
        session, experiment, status=ExperimentStatus.FAILED, error_summary=message
    )


def process_next(
    session_factory: sessionmaker[Session],
    storage: StorageAdapter,
    *,
    job_timeout_seconds: int = 3600,
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
) -> bool:
    """Claim and run one queued experiment. Returns True if a job was processed.

    Never raises: any failure is recorded on the experiment (or logged if even that fails) so
    the worker loop keeps going.
    """
    try:
        with session_factory() as session:
            repo.fail_stale_experiments(session, job_timeout_seconds)
            experiment = repo.claim_next_queued(session)
            if experiment is None:
                return False
            logger.info("Claimed experiment %s", experiment.experiment_id)
            try:
                run_experiment(session, storage, experiment, max_artifact_bytes=max_artifact_bytes)
            except JobFailure as failure:
                _fail(session, experiment, str(failure))
            except Exception:
                logger.exception("Experiment %s failed", experiment.experiment_id)
                _fail(session, experiment, UNEXPECTED_FAILURE)
            logger.info("Finished experiment %s: %s", experiment.experiment_id, experiment.status)
            return True
    except Exception:
        logger.exception("Worker iteration failed")
        return False


def run_loop(
    session_factory: sessionmaker[Session],
    storage: StorageAdapter,
    *,
    poll_seconds: float,
    job_timeout_seconds: int,
    should_stop: Callable[[], bool],
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
    sleep: Callable[[float], object] = time.sleep,
) -> None:
    """Poll for queued experiments until `should_stop()` is true."""
    while not should_stop():
        if not process_next(
            session_factory,
            storage,
            job_timeout_seconds=job_timeout_seconds,
            max_artifact_bytes=max_artifact_bytes,
        ):
            sleep(poll_seconds)
