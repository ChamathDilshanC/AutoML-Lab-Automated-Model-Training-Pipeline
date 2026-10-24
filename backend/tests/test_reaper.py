"""Abandoned jobs: the stale-experiment reaper, and a worker that finishes after being reaped."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.time import utc_now
from app.db import experiments as repo
from app.db.models import Experiment, RegisteredModel
from app.services.reaper import run_reaper
from app.services.storage import LocalStorage
from tests.data import (
    classification_csv,
    classification_payload,
    insert_experiment,
    ready_dataset,
)
from worker import jobs
from worker.jobs import process_next

TIMEOUT = 1800


def status_of(session_factory: sessionmaker[Session], name: str) -> str:
    with session_factory() as session:
        experiment = session.get(Experiment, name)
        assert experiment is not None
        return experiment.status


@pytest.fixture
def dataset_id(client: TestClient) -> str:
    return ready_dataset(client, classification_csv())


def test_the_default_timeout_is_thirty_minutes() -> None:
    assert Settings().job_timeout_seconds == 1800


def test_only_stale_running_experiments_are_failed(
    session_factory: sessionmaker[Session], dataset_id: str
) -> None:
    now = utc_now()
    old = now - timedelta(seconds=TIMEOUT + 60)
    with session_factory() as session:
        insert_experiment(session, dataset_id, "ex_stale", now, status="RUNNING", started_at=old)
        insert_experiment(session, dataset_id, "ex_fresh", now, status="RUNNING", started_at=now)
        insert_experiment(session, dataset_id, "ex_queued", old, status="QUEUED")
        insert_experiment(session, dataset_id, "ex_done", old, status="SUCCEEDED", started_at=old)

    assert repo.reap_stale(session_factory, TIMEOUT) == 1

    assert status_of(session_factory, "ex_stale") == "FAILED"
    assert status_of(session_factory, "ex_fresh") == "RUNNING"
    assert status_of(session_factory, "ex_queued") == "QUEUED"
    assert status_of(session_factory, "ex_done") == "SUCCEEDED"
    with session_factory() as session:
        stale = session.get(Experiment, "ex_stale")
        assert stale is not None
        assert stale.error_summary == repo.STALE_MESSAGE and stale.finished_at is not None
    assert repo.reap_stale(session_factory, TIMEOUT) == 0  # nothing left to do


def test_the_background_reaper_runs_repeatedly_and_stops_on_request(
    session_factory: sessionmaker[Session], dataset_id: str
) -> None:
    now = utc_now()
    with session_factory() as session:
        insert_experiment(
            session, dataset_id, "ex_a", now, status="RUNNING", started_at=now - timedelta(hours=1)
        )

    async def scenario() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(run_reaper(session_factory, TIMEOUT, 0.05, stop))
        await asyncio.sleep(0.3)
        assert status_of(session_factory, "ex_a") == "FAILED"
        # A second one that goes stale later is also picked up by a later pass.
        with session_factory() as session:
            insert_experiment(
                session,
                dataset_id,
                "ex_b",
                now,
                status="RUNNING",
                started_at=now - timedelta(hours=2),
            )
        await asyncio.sleep(0.3)
        assert status_of(session_factory, "ex_b") == "FAILED"
        stop.set()
        await asyncio.wait_for(
            task, timeout=2
        )  # exits promptly instead of sleeping out its interval

    asyncio.run(scenario())


def test_the_reaper_survives_a_failing_pass(
    session_factory: sessionmaker[Session], dataset_id: str
) -> None:
    now = utc_now()
    with session_factory() as session:
        insert_experiment(
            session, dataset_id, "ex_a", now, status="RUNNING", started_at=now - timedelta(hours=1)
        )
    calls = {"n": 0}

    def flaky_factory() -> Session:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database temporarily unavailable")
        return session_factory()

    async def scenario() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(run_reaper(flaky_factory, TIMEOUT, 0.05, stop))  # type: ignore[arg-type]
        await asyncio.sleep(0.3)
        stop.set()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    assert calls["n"] >= 2
    assert status_of(session_factory, "ex_a") == "FAILED"


def test_the_worker_also_reaps_on_every_poll(
    session_factory: sessionmaker[Session], storage: LocalStorage, dataset_id: str
) -> None:
    now = utc_now()
    with session_factory() as session:
        insert_experiment(
            session, dataset_id, "ex_a", now, status="RUNNING", started_at=now - timedelta(hours=1)
        )
    assert process_next(session_factory, storage, job_timeout_seconds=TIMEOUT) is False
    assert status_of(session_factory, "ex_a") == "FAILED"


def test_finishing_never_overwrites_an_outcome_set_by_the_reaper(
    session_factory: sessionmaker[Session], dataset_id: str
) -> None:
    now = utc_now()
    with session_factory() as session:
        experiment = insert_experiment(
            session, dataset_id, "ex_a", now, status="RUNNING", started_at=now - timedelta(hours=1)
        )
        repo.fail_stale_experiments(session, TIMEOUT)
        repo.finish_experiment(session, experiment, status="SUCCEEDED")  # type: ignore[arg-type]
        assert experiment.status == "FAILED"
        assert experiment.error_summary == repo.STALE_MESSAGE


def test_a_worker_that_finishes_after_being_reaped_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    dataset_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_id = client.post(
        "/api/v1/experiments",
        json=classification_payload(dataset_id, algorithms=["decision_tree"]),
    ).json()["experiment_id"]
    real_train = jobs.train_model

    def reaped_while_training(*args: object, **kwargs: object) -> object:
        with session_factory() as other:  # the reaper decides this job is abandoned
            repo.fail_stale_experiments(other, timeout_seconds=-1)
        return real_train(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(jobs, "train_model", reaped_while_training)
    assert process_next(session_factory, storage) is True

    after = client.get(f"/api/v1/experiments/{experiment_id}").json()
    assert after["status"] == "FAILED"
    assert after["error_summary"] == repo.STALE_MESSAGE  # the reaper's verdict stands
    with session_factory() as session:
        assert not list(session.scalars(select(RegisteredModel)))  # no model was registered
    assert (
        not list((tmp_path / "storage" / "models").rglob("*.*"))
        if (tmp_path / "storage" / "models").exists()
        else True
    )
