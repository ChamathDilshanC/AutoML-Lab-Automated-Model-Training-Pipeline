"""AWS mode: S3 storage, presigned uploads, SQS job hand-off, and the IAM policies that fit them.

Nothing here talks to AWS. `moto` replaces the AWS APIs in-process, with throwaway credentials, so
no account, network or money is involved.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
import requests
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db import experiments as experiment_repo
from app.db.models import Experiment, ExperimentRun
from app.services import aws as aws_services
from app.services.job_queue import (
    JobPublishError,
    NullPublisher,
    QueueMessage,
    SqsQueue,
    parse_experiment_id,
)
from app.services.models import clear_model_cache
from app.services.storage import FileTooLargeError, LocalStorage, S3Storage, StorageError
from tests import data
from tests.conftest import TestUser
from tests.hclutil import policy_actions
from worker import jobs

REGION = "eu-west-1"
BUCKET = "automl-test-bucket"
FAST = {"algorithms": ["logistic_regression", "decision_tree"]}


@dataclass
class Aws:
    s3: Any
    sqs: Any
    queue_url: str


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[Aws]:
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        sqs = boto3.client("sqs", region_name=REGION)
        url = sqs.create_queue(QueueName="automl-experiments-queue")["QueueUrl"]
        yield Aws(s3, sqs, url)


@pytest.fixture
def app_env(aws: Aws) -> dict[str, str]:
    """Run the whole app in cloud mode against the mocked AWS."""
    return {
        "STORAGE_MODE": "s3",
        "JOB_MODE": "sqs",
        "S3_BUCKET": BUCKET,
        "SQS_QUEUE_URL": aws.queue_url,
        "AWS_REGION": REGION,
    }


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    clear_model_cache()


def settings_for(aws: Aws) -> Settings:
    return Settings(
        storage_mode="s3",
        s3_bucket=BUCKET,
        job_mode="sqs",
        sqs_queue_url=aws.queue_url,
        aws_region=REGION,
    )


@pytest.fixture
def s3_storage(aws: Aws) -> S3Storage:
    """Built exactly as the app and worker build theirs (SigV4, regional virtual-host URLs)."""
    return S3Storage(aws_services.make_s3_client(settings_for(aws)), BUCKET)


@pytest.fixture
def queue(aws: Aws) -> SqsQueue:
    return SqsQueue(aws.sqs, aws.queue_url, wait_seconds=0)  # no long wait in tests


def object_keys(aws: Aws, prefix: str = "") -> list[str]:
    listing = aws.s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return sorted(item["Key"] for item in listing.get("Contents", []))


def queue_counts(aws: Aws) -> tuple[int, int]:
    """(waiting, in flight) messages."""
    attrs = aws.sqs.get_queue_attributes(QueueUrl=aws.queue_url, AttributeNames=["All"])[
        "Attributes"
    ]
    return int(attrs["ApproximateNumberOfMessages"]), int(
        attrs["ApproximateNumberOfMessagesNotVisible"]
    )


def register(client: TestClient, content: bytes, filename: str = "data.csv") -> dict[str, Any]:
    response = client.post(
        "/api/v1/datasets", json={"filename": filename, "size_bytes": len(content)}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def put_to_storage(target: dict[str, Any], content: bytes) -> requests.Response:
    """What the browser does: PUT straight to the presigned URL, with no bearer token."""
    return requests.put(target["url"], data=content, headers=target["headers"], timeout=10)


# --- settings and wiring ------------------------------------------------------------------------


def test_the_defaults_need_no_aws() -> None:
    settings = Settings()
    assert (settings.storage_mode, settings.job_mode) == ("local", "db")
    assert isinstance(aws_services.build_storage(settings), LocalStorage)
    assert isinstance(aws_services.build_publisher(settings), NullPublisher)


def test_cloud_modes_need_their_resources() -> None:
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(storage_mode="s3")
    with pytest.raises(ValueError, match="SQS_QUEUE_URL"):
        Settings(job_mode="sqs")
    with pytest.raises(ValueError):
        Settings(storage_mode="floppy")  # type: ignore[arg-type]
    for bad in (0, 3601):
        with pytest.raises(ValueError, match="PRESIGN"):
            Settings(s3_presign_expires_seconds=bad)
    with pytest.raises(ValueError, match="SQS_WAIT"):
        Settings(sqs_wait_seconds=21)


def test_the_builders_follow_the_settings(aws: Aws) -> None:
    settings = Settings(
        storage_mode="s3", s3_bucket=BUCKET, job_mode="sqs", sqs_queue_url=aws.queue_url
    )
    assert isinstance(aws_services.build_storage(settings), S3Storage)
    assert isinstance(aws_services.build_publisher(settings), SqsQueue)


# --- S3 storage ---------------------------------------------------------------------------------


def test_objects_round_trip(s3_storage: S3Storage, aws: Aws) -> None:
    import io

    assert s3_storage.save("datasets/u/d/source.csv", io.BytesIO(b"a,b\n1,2\n"), 100) == 8
    assert s3_storage.exists("datasets/u/d/source.csv")
    assert s3_storage.size("datasets/u/d/source.csv") == 8
    assert s3_storage.read("datasets/u/d/source.csv") == b"a,b\n1,2\n"
    s3_storage.save("datasets/u/d/source.csv", io.BytesIO(b"new"), 100)  # overwrite
    assert s3_storage.read("datasets/u/d/source.csv") == b"new"
    s3_storage.delete("datasets/u/d/source.csv")
    assert not s3_storage.exists("datasets/u/d/source.csv")
    s3_storage.delete("datasets/u/d/source.csv")  # deleting twice is fine


def test_missing_objects_raise_file_not_found(s3_storage: S3Storage) -> None:
    for call in (s3_storage.read, s3_storage.size):
        with pytest.raises(FileNotFoundError):
            call("datasets/u/none/source.csv")
    assert s3_storage.exists("datasets/u/none/source.csv") is False


def test_the_size_cap_stops_a_save_and_leaves_nothing(s3_storage: S3Storage, aws: Aws) -> None:
    import io

    with pytest.raises(FileTooLargeError):
        s3_storage.save("datasets/u/d/source.csv", io.BytesIO(b"x" * 50), 10)
    assert object_keys(aws) == []


@pytest.mark.parametrize("key", ["", "/abs", "a/../b", "a//b", "a\\b", "x/" * 600])
def test_unsafe_keys_are_refused(s3_storage: S3Storage, key: str) -> None:
    with pytest.raises(StorageError, match="Invalid storage key"):
        s3_storage.size(key)


def test_delete_prefix_removes_only_that_folder(s3_storage: S3Storage, aws: Aws) -> None:
    import io

    for key in (
        "models/md_1/1/model.joblib",
        "models/md_1/1/metadata.json",
        "models/md_10/1/model.joblib",
        "models/md_2/1/model.joblib",
    ):
        s3_storage.save(key, io.BytesIO(b"x"), 10)
    s3_storage.delete_prefix("models/md_1")
    # md_10 starts with the text "md_1": a careless prefix match would have deleted it too.
    assert object_keys(aws) == ["models/md_10/1/model.joblib", "models/md_2/1/model.joblib"]
    s3_storage.delete_prefix("models/md_1/")  # trailing slash and an empty folder are fine
    s3_storage.delete_prefix("models/nothing")


def test_delete_prefix_works_in_batches(
    s3_storage: S3Storage, aws: Aws, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from app.services import storage as storage_module

    monkeypatch.setattr(storage_module, "DELETE_BATCH", 2)
    for i in range(5):
        s3_storage.save(f"datasets/u/d/part-{i}.csv", io.BytesIO(b"x"), 10)
    s3_storage.delete_prefix("datasets/u/d")
    assert object_keys(aws) == []


def test_provider_errors_never_reach_callers() -> None:
    class Broken:
        def __getattr__(self, name: str) -> Any:
            def fail(*args: Any, **kwargs: Any) -> Any:
                raise ClientError(
                    {"Error": {"Code": "AccessDenied", "Message": "secret-bucket-name denied"}},
                    name,
                )

            return fail

    import io

    storage = S3Storage(Broken(), "secret-bucket-name")
    calls = (
        lambda: storage.read("a/b"),
        lambda: storage.size("a/b"),
        lambda: storage.delete("a/b"),
        lambda: storage.save("a/b", io.BytesIO(b"x"), 10),
        lambda: storage.upload_target("a/b", 1, "text/csv"),
    )
    for call in calls:
        with pytest.raises(StorageError) as raised:
            call()
        assert "secret-bucket-name" not in str(raised.value)
    with pytest.raises(StorageError):
        storage.delete_prefix("a/b")


# --- presigned uploads --------------------------------------------------------------------------


def test_the_presigned_url_is_short_lived_scoped_and_pins_the_size(s3_storage: S3Storage) -> None:
    target = s3_storage.upload_target("datasets/u/d/source.csv", 1234, "text/csv")
    assert target is not None
    assert (target.method, target.headers, target.requires_auth) == (
        "PUT",
        {"Content-Type": "text/csv"},
        False,
    )
    assert target.expires_in_seconds == 300
    url = urlparse(target.url)
    assert url.scheme == "https"
    # Regional virtual-hosted style: the global endpoint redirects uploads to other regions.
    assert url.netloc == f"{BUCKET}.s3.{REGION}.amazonaws.com"
    assert url.path == "/datasets/u/d/source.csv"
    query = parse_qs(url.query)
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    # Part of the signature, so S3 itself refuses a different length or type:
    assert set(query["X-Amz-SignedHeaders"][0].split(";")) >= {"content-length", "content-type"}
    assert "X-Amz-Signature" in url.query and "secret" not in target.url.lower()


def test_path_style_urls_are_available_for_s3_compatible_emulators(aws: Aws) -> None:
    settings = settings_for(aws).model_copy(update={"s3_addressing_style": "path"})
    storage = S3Storage(aws_services.make_s3_client(settings), BUCKET)
    target = storage.upload_target("datasets/u/d/source.csv", 10, "text/csv")
    assert target is not None
    url = urlparse(target.url)
    assert (
        url.netloc == f"s3.{REGION}.amazonaws.com"
        and url.path == f"/{BUCKET}/datasets/u/d/source.csv"
    )
    with pytest.raises(ValueError):
        Settings(s3_addressing_style="subdomain")  # type: ignore[arg-type]


def test_the_expiry_is_configurable(aws: Aws) -> None:
    storage = S3Storage(
        aws_services.make_s3_client(settings_for(aws)), BUCKET, presign_expires_seconds=60
    )
    target = storage.upload_target("datasets/u/d/source.csv", 10, "text/csv")
    assert target is not None and "X-Amz-Expires=60" in target.url


# --- the dataset flow against S3 ----------------------------------------------------------------


def test_register_upload_directly_to_storage_then_validate(
    client: TestClient, aws: Aws, alice: TestUser
) -> None:
    csv = data.classification_csv()
    body = register(client, csv)
    target = body["upload"]
    assert target["requires_auth"] is False
    assert (
        BUCKET in target["url"]
        and "datasets" in target["url"]
        and body["dataset_id"] in target["url"]
    )
    assert body["status"] == "PENDING_UPLOAD"
    assert object_keys(aws) == []  # nothing stored until the browser sends it

    assert put_to_storage(target, csv).status_code == 200
    assert object_keys(aws) == [f"datasets/{alice.user_id}/{body['dataset_id']}/source.csv"]

    report = client.post(f"/api/v1/datasets/{body['dataset_id']}/validate").json()
    assert report["status"] == "READY" and report["row_count"] == 80


def test_validating_before_the_upload_is_a_conflict(client: TestClient) -> None:
    body = register(client, data.classification_csv())
    response = client.post(f"/api/v1/datasets/{body['dataset_id']}/validate")
    assert response.status_code == 409


def test_a_wrong_sized_object_is_rejected_and_removed(client: TestClient, aws: Aws) -> None:
    """The signature pins the size on real S3. The mock does not check signatures, so this proves
    the independent check at validation time instead."""
    csv = data.classification_csv()
    body = register(client, csv)
    assert put_to_storage(body["upload"], csv[:-20]).status_code == 200
    report = client.post(f"/api/v1/datasets/{body['dataset_id']}/validate").json()
    assert report["status"] == "REJECTED" and "declared size" in report["message"]
    assert object_keys(aws) == []


def test_the_local_upload_route_is_unavailable_in_cloud_mode(client: TestClient) -> None:
    csv = data.classification_csv()
    body = register(client, csv)
    response = client.put(f"/api/v1/datasets/{body['dataset_id']}/content", content=csv)
    assert response.status_code == 409


def test_a_declared_size_over_the_limit_is_refused_before_a_url_is_issued(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/datasets", json={"filename": "big.csv", "size_bytes": 10**9})
    assert response.status_code == 413
    assert "upload" not in response.text


def test_deleting_a_dataset_empties_its_folders_in_the_bucket(
    client: TestClient, aws: Aws, s3_storage: S3Storage, session_factory: sessionmaker[Session]
) -> None:
    dataset_id = _ready(client)
    model_id = data.trained_model_id(
        client, session_factory, s3_storage, b"", dataset_id=dataset_id, **FAST
    )
    assert any(k.startswith(f"models/{model_id}/") for k in object_keys(aws))
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
    assert object_keys(aws) == []


def _ready(client: TestClient, content: bytes | None = None) -> str:
    csv = content or data.classification_csv()
    body = register(client, csv)
    assert put_to_storage(body["upload"], csv).status_code == 200
    assert (
        client.post(f"/api/v1/datasets/{body['dataset_id']}/validate").json()["status"] == "READY"
    )
    return str(body["dataset_id"])


# --- SQS job hand-off ---------------------------------------------------------------------------


def create_experiment(client: TestClient, dataset_id: str, **headers: str) -> Any:
    return client.post(
        "/api/v1/experiments",
        json=data.classification_payload(dataset_id, **FAST),
        headers=headers,
    )


def receive_one(aws: Aws) -> dict[str, Any]:
    messages = aws.sqs.receive_message(QueueUrl=aws.queue_url, MaxNumberOfMessages=1).get(
        "Messages", []
    )
    assert len(messages) == 1
    return dict(messages[0])


def test_creating_an_experiment_sends_only_its_id_to_the_queue(
    client: TestClient, aws: Aws
) -> None:
    dataset_id = _ready(client)
    created = create_experiment(client, dataset_id)
    assert created.status_code == 202 and created.json()["status"] == "QUEUED"
    message = receive_one(aws)
    assert json.loads(message["Body"]) == {
        "experiment_id": created.json()["experiment_id"],
        "version": 1,
    }


def test_a_replayed_request_does_not_send_a_second_message(client: TestClient, aws: Aws) -> None:
    dataset_id = _ready(client)
    first = create_experiment(client, dataset_id, **{"Idempotency-Key": "k-1"})
    second = create_experiment(client, dataset_id, **{"Idempotency-Key": "k-1"})
    assert first.json()["experiment_id"] == second.json()["experiment_id"]
    assert sum(queue_counts(aws)) == 1


def test_if_the_queue_is_down_the_experiment_is_not_left_queued(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    aws: Aws,
) -> None:
    class DownQueue:
        def publish(self, experiment_id: str) -> None:
            raise JobPublishError("queue unavailable: secret-queue-url")

    dataset_id = _ready(client)
    real_publisher = app.state.publisher
    app.state.publisher = DownQueue()
    failed = create_experiment(client, dataset_id, **{"Idempotency-Key": "retry-me"})
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert failed.headers["Retry-After"] == "5"
    assert "secret-queue-url" not in failed.text
    with session_factory() as session:
        assert list(session.scalars(select(Experiment))) == []  # nothing orphaned

    app.state.publisher = real_publisher  # the same request now succeeds, with the same key
    assert (
        create_experiment(client, dataset_id, **{"Idempotency-Key": "retry-me"}).status_code == 202
    )


def test_the_worker_runs_a_queued_job_and_deletes_the_message(
    client: TestClient,
    aws: Aws,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
) -> None:
    dataset_id = _ready(client)
    experiment_id = create_experiment(client, dataset_id).json()["experiment_id"]
    message = queue.receive()
    assert message is not None and message.receive_count == 1

    assert jobs.process_message(session_factory, s3_storage, queue, message) == "done"

    experiment = client.get(f"/api/v1/experiments/{experiment_id}").json()
    assert experiment["status"] == "SUCCEEDED"
    assert client.get(f"/api/v1/experiments/{experiment_id}/results").json()["model_id"]
    assert queue_counts(aws) == (0, 0)  # deleted, not just hidden


def test_a_duplicate_delivery_runs_nothing_twice(
    client: TestClient,
    aws: Aws,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
) -> None:
    dataset_id = _ready(client)
    experiment_id = create_experiment(client, dataset_id).json()["experiment_id"]
    first = queue.receive()
    assert first is not None
    assert jobs.process_message(session_factory, s3_storage, queue, first) == "done"

    # SQS delivers at least once: the same job arrives again.
    aws.sqs.send_message(
        QueueUrl=aws.queue_url, MessageBody=json.dumps({"experiment_id": experiment_id})
    )
    again = queue.receive()
    assert again is not None
    assert jobs.process_message(session_factory, s3_storage, queue, again) == "skipped"

    with session_factory() as session:
        runs = list(session.scalars(select(ExperimentRun)))
    assert len(runs) == 2  # the two algorithms, once
    assert queue_counts(aws) == (0, 0)


@pytest.mark.parametrize(
    ("body", "outcome"),
    [
        ("not json", "discarded"),
        ("[]", "discarded"),
        (json.dumps({"nope": 1}), "discarded"),
        (json.dumps({"experiment_id": "ex_short"}), "discarded"),
        (json.dumps({"experiment_id": "ex_" + "g" * 32}), "discarded"),
        (json.dumps({"experiment_id": "ex_" + "0" * 32}), "skipped"),  # well formed, unknown
    ],
)
def test_bad_or_orphaned_messages_are_dropped_not_retried_forever(
    aws: Aws,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
    body: str,
    outcome: str,
) -> None:
    aws.sqs.send_message(QueueUrl=aws.queue_url, MessageBody=body)
    message = queue.receive()
    assert message is not None
    assert jobs.process_message(session_factory, s3_storage, queue, message) == outcome
    assert queue_counts(aws) == (0, 0)


def test_a_message_cannot_change_what_runs(
    client: TestClient,
    aws: Aws,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
) -> None:
    dataset_id = _ready(client)
    experiment_id = create_experiment(client, dataset_id).json()["experiment_id"]
    receive_one(aws)  # drop the genuine message
    aws.sqs.send_message(
        QueueUrl=aws.queue_url,
        MessageBody=json.dumps(
            {"experiment_id": experiment_id, "algorithms": ["os.system"], "target_column": "x1"}
        ),
    )
    message = queue.receive()
    assert message is not None
    assert jobs.process_message(session_factory, s3_storage, queue, message) == "done"
    runs = client.get(f"/api/v1/experiments/{experiment_id}/results").json()["runs"]
    assert sorted(r["algorithm"] for r in runs) == ["decision_tree", "logistic_regression"]


def test_if_the_database_is_down_the_message_is_kept_for_redelivery(
    client: TestClient,
    aws: Aws,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_id = _ready(client)
    experiment_id = create_experiment(client, dataset_id).json()["experiment_id"]
    message = queue.receive()
    assert message is not None

    def db_down(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(experiment_repo, "claim_experiment", db_down)
    assert jobs.process_message(session_factory, s3_storage, queue, message) == "retry"
    assert queue_counts(aws) == (0, 1)  # still there, just invisible until the timeout

    monkeypatch.undo()
    assert client.get(f"/api/v1/experiments/{experiment_id}").json()["status"] == "QUEUED"


def test_a_failed_delete_is_not_fatal(
    client: TestClient,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_id = _ready(client)
    create_experiment(client, dataset_id)
    message = queue.receive()
    assert message is not None

    def cannot_delete(_: QueueMessage) -> None:
        raise RuntimeError("network")

    monkeypatch.setattr(queue, "delete", cannot_delete)
    assert jobs.process_message(session_factory, s3_storage, queue, message) == "done"


def test_the_loop_processes_messages_and_survives_receive_errors(
    client: TestClient,
    aws: Aws,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
) -> None:
    first = create_experiment(client, _ready(client)).json()["experiment_id"]
    second = create_experiment(client, _ready(client)).json()["experiment_id"]

    class FlakyQueue:
        """Fails its first receive, then behaves like the real queue."""

        def __init__(self) -> None:
            self.failed = False

        def receive(self) -> QueueMessage | None:
            if not self.failed:
                self.failed = True
                raise RuntimeError("temporary network error")
            return queue.receive()

        def delete(self, message: QueueMessage) -> None:
            queue.delete(message)

    sleeps: list[float] = []
    state = {"calls": 0}

    def should_stop() -> bool:
        state["calls"] += 1
        return state["calls"] > 4

    jobs.run_sqs_loop(
        session_factory,
        s3_storage,
        FlakyQueue(),  # type: ignore[arg-type]
        job_timeout_seconds=1800,
        max_artifact_bytes=10**8,
        should_stop=should_stop,
        on_error_sleep=sleeps.append,
    )
    assert sleeps == [5.0]
    for experiment_id in (first, second):
        assert client.get(f"/api/v1/experiments/{experiment_id}").json()["status"] == "SUCCEEDED"
    assert queue_counts(aws) == (0, 0)


def test_the_sqs_loop_also_reaps_abandoned_jobs(
    client: TestClient,
    s3_storage: S3Storage,
    queue: SqsQueue,
    session_factory: sessionmaker[Session],
) -> None:
    from datetime import timedelta

    from app.core.time import utc_now

    dataset_id = _ready(client)
    with session_factory() as session:
        data.insert_experiment(
            session,
            dataset_id,
            "ex_stuck",
            utc_now(),
            status="RUNNING",
            started_at=utc_now() - timedelta(hours=2),
        )
    jobs.run_sqs_loop(
        session_factory,
        s3_storage,
        queue,
        job_timeout_seconds=1800,
        max_artifact_bytes=10**8,
        should_stop=iter([False, True]).__next__,
    )
    with session_factory() as session:
        stuck = session.get(Experiment, "ex_stuck")
        assert stuck is not None and stuck.status == "FAILED"


def test_long_polling_is_used() -> None:
    class Spy:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def receive_message(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            return {}

    spy = Spy()
    assert SqsQueue(spy, "https://sqs.example/queue").receive() is None
    assert spy.calls[0]["WaitTimeSeconds"] == 20 and spy.calls[0]["MaxNumberOfMessages"] == 1


def test_parsing_only_accepts_our_message_shape() -> None:
    good = "ex_" + "a1" * 16
    assert parse_experiment_id(json.dumps({"experiment_id": good})) == good
    for bad in (
        good,
        "{",
        "null",
        json.dumps({"experiment_id": 5}),
        json.dumps({"experiment_id": good.upper()}),
    ):
        assert parse_experiment_id(bad) is None


# --- a full cloud run, and what it needs from IAM -----------------------------------------------

ACTION_FOR_OPERATION = {
    "PutObject": "s3:PutObject",
    "CreateMultipartUpload": "s3:PutObject",
    "UploadPart": "s3:PutObject",
    "CompleteMultipartUpload": "s3:PutObject",
    "AbortMultipartUpload": "s3:AbortMultipartUpload",
    "GetObject": "s3:GetObject",
    "HeadObject": "s3:GetObject",
    "DeleteObject": "s3:DeleteObject",
    "DeleteObjects": "s3:DeleteObject",
    "ListObjectsV2": "s3:ListBucket",
    "SendMessage": "sqs:SendMessage",
    "ReceiveMessage": "sqs:ReceiveMessage",
    "DeleteMessage": "sqs:DeleteMessage",
}


def record_operations(client: Any, into: set[str]) -> None:
    client.meta.events.register(
        "before-call.*.*",
        lambda model, **_: into.add(model.name),  # type: ignore[arg-type]
    )


def test_the_iam_policies_cover_exactly_what_the_code_calls(
    app: FastAPI,
    client: TestClient,
    aws: Aws,
    session_factory: sessionmaker[Session],
) -> None:
    """Run the whole cloud flow, record every AWS operation, and compare it with iam.tf.

    The API and the worker use separate clients, so each side's calls are checked against its own
    policy. A new AWS call fails this test until the policy (and therefore the review) catches up;
    a policy that grants more than the code uses fails it too.
    """
    api_ops: set[str] = set()
    worker_ops: set[str] = set()
    record_operations(app.state.storage._client, api_ops)
    record_operations(app.state.publisher._client, api_ops)

    worker_s3 = aws_services.make_s3_client(settings_for(aws))
    worker_sqs = aws_services.make_sqs_client(settings_for(aws))
    record_operations(worker_s3, worker_ops)
    record_operations(worker_sqs, worker_ops)
    worker_storage = S3Storage(worker_s3, BUCKET)
    worker_queue = SqsQueue(worker_sqs, aws.queue_url, wait_seconds=0)

    dataset_id = _ready(client)
    experiment_id = create_experiment(client, dataset_id).json()["experiment_id"]
    message = worker_queue.receive()
    assert message is not None
    assert jobs.process_message(session_factory, worker_storage, worker_queue, message) == "done"
    model_id = client.get(f"/api/v1/experiments/{experiment_id}/results").json()["model_id"]
    client.post(f"/api/v1/models/{model_id}/approve", json={"confirm": True})
    assert (
        client.post(
            f"/api/v1/models/{model_id}/predict",
            json={"instances": [{"x1": 1.0, "x2": 0.0, "color": "red"}]},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204

    unknown = (api_ops | worker_ops) - set(ACTION_FOR_OPERATION)
    assert not unknown, f"AWS calls with no IAM mapping in this test: {sorted(unknown)}"
    api_needed = {ACTION_FOR_OPERATION[op] for op in api_ops}
    # The API never calls PutObject itself: it signs an upload URL, and S3 authorises that upload
    # as whoever signed it. So the API's identity needs s3:PutObject all the same.
    api_needed.add("s3:PutObject")
    worker_needed = {ACTION_FOR_OPERATION[op] for op in worker_ops}

    # The API must be able to do what it did, and nothing a worker should do.
    assert api_needed <= policy_actions("api"), api_needed - policy_actions("api")
    assert worker_needed <= policy_actions("worker"), worker_needed - policy_actions("worker")
    assert api_needed >= {
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "sqs:SendMessage",
    }
    assert worker_needed >= {
        "s3:GetObject",
        "s3:PutObject",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
    }

    # ...and the policies may only grant what is plausible for that runtime.
    assert policy_actions("api") <= {
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:AbortMultipartUpload",
        "s3:ListBucket",
        "sqs:SendMessage",
    }
    assert policy_actions("worker") <= {
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:AbortMultipartUpload",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
    }
    assert "sqs:ReceiveMessage" not in api_needed and "sqs:SendMessage" not in worker_needed
