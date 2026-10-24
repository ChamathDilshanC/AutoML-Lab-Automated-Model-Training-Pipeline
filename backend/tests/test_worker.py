"""Tests for the training worker: it runs queued experiments outside any web request."""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utc_now
from app.db import experiments as repo
from app.db.models import Experiment
from app.services.storage import LocalStorage
from tests.data import (
    classification_csv,
    classification_payload,
    rare_class_csv,
    ready_dataset,
    regression_csv,
    regression_payload,
)
from worker import jobs
from worker.jobs import _clean_metrics, process_next, run_loop

BACKEND_DIR = Path(__file__).resolve().parent.parent


def queue(client: TestClient, payload: dict[str, object]) -> str:
    response = client.post("/api/v1/experiments", json=payload)
    assert response.status_code == 202, response.text
    return str(response.json()["experiment_id"])


def status_of(client: TestClient, experiment_id: str) -> dict:
    return dict(client.get(f"/api/v1/experiments/{experiment_id}").json())


def results_of(client: TestClient, experiment_id: str) -> dict:
    response = client.get(f"/api/v1/experiments/{experiment_id}/results")
    assert response.status_code == 200, response.text
    return dict(response.json())


# --- end to end ---------------------------------------------------------------------------------


def test_worker_runs_a_queued_classification_experiment(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = queue(client, classification_payload(dataset_id))
    assert status_of(client, experiment_id)["status"] == "QUEUED"

    assert process_next(session_factory, storage) is True

    experiment = status_of(client, experiment_id)
    assert experiment["status"] == "SUCCEEDED"
    assert experiment["started_at"] and experiment["finished_at"]
    assert experiment["error_summary"] is None

    board = results_of(client, experiment_id)
    runs = board["runs"]
    assert sorted(run["algorithm"] for run in runs) == [
        "decision_tree",
        "logistic_regression",
        "random_forest",
    ]
    assert [run["rank"] for run in runs] == [1, 2, 3]
    scores = [run["metrics"]["f1"] for run in runs]
    assert scores == sorted(scores, reverse=True)  # f1: higher is better
    assert board["selected_run_id"] == runs[0]["run_id"]
    assert board["higher_is_better"] is True
    assert board["selection_reason"] == {
        "metric": "f1",
        "direction": "higher_is_better",
        "evaluated_on": "held_out_test_set",
        "tie_breaker": "algorithm_name",
    }
    assert set(runs[0]["metrics"]) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
    assert all(run["status"] == "SUCCEEDED" and run["duration_seconds"] >= 0 for run in runs)
    assert board["split"]["strategy"] == "stratified_random"
    assert board["split"]["n_train"] + board["split"]["n_test"] == 80
    assert board["library_versions"]["scikit-learn"]


def test_regression_ranks_lower_rmse_first(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    dataset_id = ready_dataset(client, regression_csv())
    experiment_id = queue(client, regression_payload(dataset_id))
    assert process_next(session_factory, storage) is True

    board = results_of(client, experiment_id)
    errors = [run["metrics"]["rmse"] for run in board["runs"]]
    assert errors == sorted(errors)  # rmse: lower is better
    assert board["higher_is_better"] is False
    assert board["selection_reason"]["direction"] == "lower_is_better"
    assert board["split"]["strategy"] == "random"
    assert board["runs"][0]["algorithm"] == "linear_regression"  # the data is linear


def test_same_configuration_gives_identical_results(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    first = queue(client, classification_payload(dataset_id, random_seed=7))
    second = queue(client, classification_payload(dataset_id, random_seed=7))
    assert process_next(session_factory, storage) and process_next(session_factory, storage)

    def summary(experiment_id: str) -> list[tuple]:
        return [
            (run["algorithm"], run["metrics"], run["hyperparameters"])
            for run in results_of(client, experiment_id)["runs"]
        ]

    assert summary(first) == summary(second)


def test_process_next_returns_false_when_nothing_is_queued(
    session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    assert process_next(session_factory, storage) is False


# --- failures never crash the worker ------------------------------------------------------------


def test_missing_dataset_file_fails_that_experiment_and_the_loop_continues(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    broken_dataset = ready_dataset(client, classification_csv())
    good_dataset = ready_dataset(client, classification_csv())
    with session_factory() as session:
        from app.db.models import Dataset

        storage.delete(session.get(Dataset, broken_dataset).storage_key)  # type: ignore[union-attr]
    broken = queue(client, classification_payload(broken_dataset))
    good = queue(client, classification_payload(good_dataset))

    assert process_next(session_factory, storage) is True
    assert process_next(session_factory, storage) is True

    failed = status_of(client, broken)
    assert failed["status"] == "FAILED"
    assert failed["error_summary"] == "The dataset is no longer available."
    assert status_of(client, good)["status"] == "SUCCEEDED"
    assert results_of(client, broken)["runs"] == []


def test_data_problems_found_by_the_worker_fail_with_a_safe_message(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    dataset_id = ready_dataset(client, rare_class_csv())
    experiment_id = queue(
        client,
        classification_payload(dataset_id, algorithms=["decision_tree"]),
    )
    assert process_next(session_factory, storage) is True
    experiment = status_of(client, experiment_id)
    assert experiment["status"] == "FAILED"
    assert "fewer than 2 rows" in experiment["error_summary"]


def test_one_failing_algorithm_does_not_fail_the_experiment(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_train = jobs.train_model

    def flaky(X, y, task, algorithm, **kwargs):
        if algorithm == "random_forest":
            raise RuntimeError("secret value 12345 leaked in a library message")
        return real_train(X, y, task, algorithm, **kwargs)

    monkeypatch.setattr(jobs, "train_model", flaky)
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = queue(client, classification_payload(dataset_id))
    assert process_next(session_factory, storage) is True

    assert status_of(client, experiment_id)["status"] == "SUCCEEDED"
    runs = results_of(client, experiment_id)["runs"]
    assert [run["status"] for run in runs] == ["SUCCEEDED", "SUCCEEDED", "FAILED"]  # failed last
    failed = runs[-1]
    assert failed["algorithm"] == "random_forest" and failed["rank"] is None
    assert failed["error_summary"] == "Training failed for this algorithm."
    assert "12345" not in str(runs)


def test_experiment_fails_when_every_algorithm_fails(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fails(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(jobs, "train_model", always_fails)
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = queue(client, classification_payload(dataset_id))
    assert process_next(session_factory, storage) is True

    experiment = status_of(client, experiment_id)
    assert experiment["status"] == "FAILED"
    assert experiment["error_summary"] == "No algorithm produced a usable result."
    board = results_of(client, experiment_id)
    assert board["selected_run_id"] is None and board["selection_reason"] is None
    assert [run["status"] for run in board["runs"]] == ["FAILED"] * 3


def test_unexpected_errors_are_recorded_generically(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("/private/path and 987654")

    monkeypatch.setattr(jobs, "split_data", explode)
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = queue(client, classification_payload(dataset_id))
    assert process_next(session_factory, storage) is True

    experiment = status_of(client, experiment_id)
    assert experiment["status"] == "FAILED"
    assert experiment["error_summary"] == "Unexpected error while running the experiment."


def test_nan_metrics_are_stored_as_null() -> None:
    cleaned = _clean_metrics({"a": 1.5, "b": float("nan"), "c": float("inf"), "d": None})
    assert cleaned == {"a": 1.5, "b": None, "c": None, "d": None}


# --- queue mechanics ----------------------------------------------------------------------------


def make_experiment(
    session: Session, dataset_id: str, name: str, created_at: datetime, **fields: object
) -> Experiment:
    values: dict[str, object] = {
        "experiment_id": name,
        "owner_id": "local-user",
        "dataset_id": dataset_id,
        "target_column": "label",
        "task": "classification",
        "metric": "f1",
        "algorithms": ["decision_tree"],
        "random_seed": 1,
        "test_size": 0.2,
        "status": "QUEUED",
        "created_at": created_at,
    }
    values.update(fields)
    return repo.create_experiment(session, **values)


def test_claims_are_fifo_exclusive_and_only_for_queued_jobs(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    base = datetime(2026, 1, 1)
    with session_factory() as session:
        make_experiment(session, dataset_id, "ex_late", base + timedelta(minutes=5))
        make_experiment(session, dataset_id, "ex_early", base)
        make_experiment(session, dataset_id, "ex_done", base, status="SUCCEEDED")

        first = repo.claim_next_queued(session)
        second = repo.claim_next_queued(session)
        third = repo.claim_next_queued(session)

        assert first is not None and first.experiment_id == "ex_early"
        assert first.status == "RUNNING" and first.started_at is not None
        assert second is not None and second.experiment_id == "ex_late"
        assert third is None  # ex_done is not queued; the claimed ones are not claimed twice


def test_stale_running_experiments_are_failed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    now = utc_now()
    with session_factory() as session:
        make_experiment(
            session,
            dataset_id,
            "ex_stale",
            now,
            status="RUNNING",
            started_at=now - timedelta(hours=2),
        )
        make_experiment(session, dataset_id, "ex_fresh", now, status="RUNNING", started_at=now)

        assert repo.fail_stale_experiments(session, timeout_seconds=3600) == 1

        stale = session.get(Experiment, "ex_stale")
        fresh = session.get(Experiment, "ex_fresh")
        assert stale is not None and fresh is not None
        assert stale.status == "FAILED" and stale.error_summary == repo.STALE_MESSAGE
        assert fresh.status == "RUNNING"


def test_run_loop_processes_jobs_then_idles_until_stopped(
    client: TestClient, session_factory: sessionmaker[Session], storage: LocalStorage
) -> None:
    dataset_id = ready_dataset(client, classification_csv())
    experiment_id = queue(client, classification_payload(dataset_id, algorithms=["decision_tree"]))

    idle_sleeps: list[float] = []
    state = {"iterations": 0}

    def should_stop() -> bool:
        state["iterations"] += 1
        return state["iterations"] > 3

    run_loop(
        session_factory,
        storage,
        poll_seconds=0.5,
        job_timeout_seconds=3600,
        should_stop=should_stop,
        sleep=idle_sleeps.append,
    )
    assert status_of(client, experiment_id)["status"] == "SUCCEEDED"
    assert idle_sleeps == [0.5, 0.5]  # slept only after the queue was empty


# --- independence from the web server -----------------------------------------------------------


def test_worker_does_not_import_the_web_framework() -> None:
    code = (
        "import sys, worker.main\n"
        "bad = sorted(m for m in ('fastapi', 'starlette', 'uvicorn') if m in sys.modules)\n"
        "print(bad)\n"
        "raise SystemExit(1 if bad else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"worker imported web code: {result.stdout} {result.stderr}"
