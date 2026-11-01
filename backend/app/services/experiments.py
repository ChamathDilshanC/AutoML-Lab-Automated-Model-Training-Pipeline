"""Experiment configuration, creation and result presentation.

Training itself runs in the worker process (backend/worker); nothing here trains a model.
"""

import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.time import as_utc, utc_now
from app.db import experiments as repo
from app.db.models import Dataset, Experiment, ExperimentRun
from app.schemas.datasets import DatasetStatus
from app.schemas.experiments import (
    ExperimentCreate,
    ExperimentOptions,
    ExperimentResponse,
    ExperimentRunResponse,
    ExperimentStatus,
    LeaderboardResponse,
    MetricOption,
    RunStatus,
    SelectionReason,
    TaskOptions,
)
from automl.evaluator import DEFAULT_METRIC, METRICS
from automl.tasks import Task
from automl.trainer import available_algorithms


def get_options() -> ExperimentOptions:
    def for_task(task: Task) -> TaskOptions:
        return TaskOptions(
            algorithms=available_algorithms(task),
            metrics=[
                MetricOption(name=spec.name, higher_is_better=spec.higher_is_better)
                for spec in METRICS[task].values()
            ],
            default_metric=DEFAULT_METRIC[task],
        )

    return ExperimentOptions(
        classification=for_task("classification"), regression=for_task("regression")
    )


def validate_config(dataset: Dataset, payload: ExperimentCreate) -> tuple[str, list[str]]:
    """Check an experiment configuration against the dataset's stored schema.

    Returns the resolved metric and the de-duplicated algorithm list. Checks that need the data
    itself (for example class counts) happen in the worker, which fails the experiment with a
    safe message.
    """
    if dataset.status != DatasetStatus.READY:
        raise ApiError(409, "STATE_CONFLICT", "The dataset must be validated and READY before use.")

    issues: list[dict[str, str]] = []

    columns = {column["name"]: column for column in dataset.schema_summary or []}
    column = columns.get(payload.target_column)
    if column is None:
        issues.append({"field": "target_column", "issue": "not found in this dataset"})
    elif column["missing_count"] > 0:
        issues.append({"field": "target_column", "issue": "has missing values"})
    elif column["unique_count"] < 2:
        issues.append({"field": "target_column", "issue": "needs at least two distinct values"})
    elif payload.task == "regression" and column["kind"] != "numeric":
        issues.append({"field": "target_column", "issue": "must be numeric for regression"})

    metric = payload.metric or DEFAULT_METRIC[payload.task]
    if metric not in METRICS[payload.task]:
        issues.append({"field": "metric", "issue": f"not available for {payload.task}"})

    algorithms = list(dict.fromkeys(payload.algorithms))
    allowed = available_algorithms(payload.task)
    if any(name not in allowed for name in algorithms):
        issues.append({"field": "algorithms", "issue": f"must be from {allowed}"})

    if issues:
        summary = "; ".join(f"{item['field']}: {item['issue']}" for item in issues)
        raise ApiError(
            422, "VALIDATION_ERROR", f"Invalid experiment configuration. {summary}.", issues
        )
    return metric, algorithms


def create_experiment(
    session: Session,
    owner_id: str,
    dataset: Dataset,
    payload: ExperimentCreate,
    idempotency_key: str | None,
    daily_limit: int = 0,
) -> tuple[Experiment, bool]:
    """Queue an experiment. Returns it and whether it is new.

    Repeating a request with the same idempotency key returns the first experiment, not new.
    """
    if idempotency_key:
        existing = repo.find_by_idempotency_key(session, owner_id, idempotency_key)
        if existing is not None:
            return existing, False

    if daily_limit:
        recent = repo.count_recent(session, owner_id, utc_now() - timedelta(hours=24))
        if recent >= daily_limit:
            raise ApiError(
                429,
                "RATE_LIMITED",
                "Daily experiment limit reached. Try again after the oldest experiment expires.",
                headers={"Retry-After": "86400"},
            )

    metric, algorithms = validate_config(dataset, payload)
    try:
        created = repo.create_experiment(
            session,
            experiment_id=f"ex_{uuid.uuid4().hex}",
            owner_id=owner_id,
            dataset_id=dataset.dataset_id,
            target_column=payload.target_column,
            task=payload.task,
            metric=metric,
            algorithms=algorithms,
            random_seed=payload.random_seed,
            test_size=payload.test_size,
            status=ExperimentStatus.QUEUED,
            idempotency_key=idempotency_key,
        )
        return created, True
    except IntegrityError:
        session.rollback()
        if idempotency_key:
            existing = repo.find_by_idempotency_key(session, owner_id, idempotency_key)
            if existing is not None:
                return existing, False
        raise


def to_response(experiment: Experiment) -> ExperimentResponse:
    return ExperimentResponse(
        experiment_id=experiment.experiment_id,
        dataset_id=experiment.dataset_id,
        task=experiment.task,  # type: ignore[arg-type]  # validated on write
        target_column=experiment.target_column,
        metric=experiment.metric,
        algorithms=list(experiment.algorithms),
        random_seed=experiment.random_seed,
        test_size=experiment.test_size,
        status=ExperimentStatus(experiment.status),
        created_at=as_utc(experiment.created_at),
        started_at=as_utc(experiment.started_at) if experiment.started_at else None,
        finished_at=as_utc(experiment.finished_at) if experiment.finished_at else None,
        error_summary=experiment.error_summary,
    )


def _run_response(run: ExperimentRun) -> ExperimentRunResponse:
    return ExperimentRunResponse(
        run_id=run.run_id,
        algorithm=run.algorithm,
        status=RunStatus(run.status),
        hyperparameters=run.hyperparameters,
        cv_score=run.cv_score,
        cv_folds=run.cv_folds,
        metrics=run.metrics,
        duration_seconds=run.duration_seconds,
        error_summary=run.error_summary,
        rank=run.rank,
    )


def build_leaderboard(
    experiment: Experiment, runs: list[ExperimentRun], model_id: str | None = None
) -> LeaderboardResponse:
    """Ranked runs first (best first), then successful but unranked runs, then failed runs."""
    spec = METRICS[experiment.task][experiment.metric]  # type: ignore[index]

    def order(run: ExperimentRun) -> tuple[int, int, str]:
        if run.status == RunStatus.FAILED:
            return (2, 0, run.algorithm)
        if run.rank is None:
            return (1, 0, run.algorithm)
        return (0, run.rank, run.algorithm)

    direction = "higher_is_better" if spec.higher_is_better else "lower_is_better"
    reason = None
    if experiment.selected_run_id:
        reason = SelectionReason(
            metric=experiment.metric,
            direction=direction,
            evaluated_on="held_out_test_set",
            tie_breaker="algorithm_name",
        )
    return LeaderboardResponse(
        experiment=to_response(experiment),
        metric=experiment.metric,
        higher_is_better=spec.higher_is_better,
        runs=[_run_response(run) for run in sorted(runs, key=order)],
        selected_run_id=experiment.selected_run_id,
        model_id=model_id,
        selection_reason=reason,
        split=experiment.split_info,
        library_versions=experiment.library_versions,
    )
