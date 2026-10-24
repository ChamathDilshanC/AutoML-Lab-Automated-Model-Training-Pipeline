"""API tests for the dataset workflow (upload, validate, read)."""

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_storage
from app.core.security import get_owner_id
from app.db.datasets import create_dataset
from app.services.datasets import sanitize_filename
from app.services.storage import LocalStorage
from tests.conftest import TestUser


def make_csv(rows: int = 30) -> bytes:
    lines = ["age,income,city,bought"]
    for i in range(rows):
        lines.append(f"{20 + i},{30000 + 500 * i},{('Paris', 'Rome', 'Oslo')[i % 3]},{i % 2}")
    return ("\n".join(lines) + "\n").encode()


def upload(client: TestClient, content: bytes, filename: str = "data.csv"):
    """Register a dataset and send its bytes. Returns the registration response, or the failed
    one if registering was refused."""
    registered = client.post(
        "/api/v1/datasets", json={"filename": filename, "size_bytes": len(content)}
    )
    if registered.status_code == 201:
        target = registered.json()["upload"]
        sent = client.put(target["url"], content=content, headers=target["headers"])
        assert sent.status_code == 204, sent.text
    return registered


def stored_files(tmp_path: Path) -> list[Path]:
    return [p for p in (tmp_path / "storage").rglob("*") if p.is_file()]


# --- happy path ---------------------------------------------------------------------------------


def test_upload_validate_and_read(client: TestClient, tmp_path: Path) -> None:
    created = upload(client, make_csv())
    assert created.status_code == 201
    assert created.headers["X-Request-ID"].startswith("req_")
    body = created.json()
    assert body["status"] == "PENDING_UPLOAD"
    assert body["upload"]["url"] == f"/api/v1/datasets/{body['dataset_id']}/content"
    assert body["created_at"].endswith("Z")  # explicit UTC
    assert body["validation"] is None
    assert "storage_key" not in body
    assert len(stored_files(tmp_path)) == 1

    dataset_id = body["dataset_id"]
    report = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert report.status_code == 200
    data = report.json()
    assert data["status"] == "READY"
    assert (data["row_count"], data["column_count"]) == (30, 4)
    kinds = {c["name"]: c["kind"] for c in data["columns"]}
    assert kinds == {
        "age": "numeric",
        "income": "numeric",
        "city": "categorical",
        "bought": "numeric",
    }
    assert any(w["code"] == "tiny_dataset" for w in data["warnings"])

    fetched = client.get(f"/api/v1/datasets/{dataset_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "READY"
    assert fetched.json()["validation"] == data
    assert fetched.json()["size_bytes"] == len(make_csv())


def test_validation_is_idempotent(client: TestClient) -> None:
    dataset_id = upload(client, make_csv()).json()["dataset_id"]
    first = client.post(f"/api/v1/datasets/{dataset_id}/validate").json()
    second = client.post(f"/api/v1/datasets/{dataset_id}/validate").json()
    assert first == second


# --- upload rejections --------------------------------------------------------------------------


def test_non_csv_extension_is_rejected(client: TestClient, tmp_path: Path) -> None:
    response = upload(client, make_csv(), filename="data.txt")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert stored_files(tmp_path) == []


def test_missing_fields_use_the_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/datasets", json={})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert {detail["field"] for detail in error["details"]} == {"filename", "size_bytes"}
    assert error["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("size", [0, -5])
def test_an_empty_or_negative_size_cannot_be_registered(client: TestClient, size: int) -> None:
    response = client.post("/api/v1/datasets", json={"filename": "a.csv", "size_bytes": size})
    assert response.status_code == 422


def test_file_over_the_limit_is_rejected_and_not_kept(client: TestClient, tmp_path: Path) -> None:
    response = upload(
        client, b"a,b\n" + b"1,2\n" * 6000
    )  # ~24 kB: over the limit, under the body cap
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert stored_files(tmp_path) == []


def test_huge_request_is_rejected_by_content_length(client: TestClient, tmp_path: Path) -> None:
    dataset_id = client.post(
        "/api/v1/datasets", json={"filename": "a.csv", "size_bytes": 10}
    ).json()["dataset_id"]
    response = client.put(f"/api/v1/datasets/{dataset_id}/content", content=b"x" * 200_000)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]
    assert stored_files(tmp_path) == []


# --- malformed files are REJECTED with safe messages --------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\n", "empty"),
        (b"a,b\n", "no rows"),
        (b"a,a\n" + b"1,2\n" * 15, "Duplicate"),
        (b"a,b\n" + b"1,2\n" * 14 + b"1,2,3\n", "same number of fields"),
        (b"a,b\n" + b"\xff\xfe\x00\x01\n" * 15, "UTF-8"),
        (b"a,b\n1,2\n3,4\n", "at least"),
        (b"a\n" + b"1\n" * 15, "column"),
    ],
)
def test_malformed_files_are_rejected(client: TestClient, content: bytes, expected: str) -> None:
    dataset_id = upload(client, content).json()["dataset_id"]
    response = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REJECTED"
    assert expected in report["message"]
    assert report["columns"] == [] and report["warnings"] == []


def test_rejected_file_is_removed_from_storage(client: TestClient, tmp_path: Path) -> None:
    dataset_id = upload(client, b"\n").json()["dataset_id"]
    assert len(stored_files(tmp_path)) == 1
    client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert stored_files(tmp_path) == []
    again = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert again.json()["status"] == "REJECTED"


def test_error_messages_do_not_echo_file_contents(client: TestClient) -> None:
    secret = b"SENSITIVE_CELL_VALUE"
    content = b"name,name\n" + secret + b",1\n" + b"x,1\n" * 15
    dataset_id = upload(client, content).json()["dataset_id"]
    report = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert secret.decode() not in report.text


# --- lookups, ownership, unexpected errors ------------------------------------------------------


def test_unknown_dataset_returns_404_envelope(client: TestClient) -> None:
    for response in (
        client.get("/api/v1/datasets/ds_missing"),
        client.post("/api/v1/datasets/ds_missing/validate"),
    ):
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "NOT_FOUND"
        assert error["request_id"] == response.headers["X-Request-ID"]


def test_other_owners_cannot_see_a_dataset(app: FastAPI, client: TestClient) -> None:
    dataset_id = upload(client, make_csv()).json()["dataset_id"]
    app.dependency_overrides[get_owner_id] = lambda: "someone-else"
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert client.post(f"/api/v1/datasets/{dataset_id}/validate").status_code == 404


def test_unexpected_errors_are_generic(app: FastAPI, client: TestClient) -> None:
    def broken_storage() -> None:
        raise RuntimeError("boom /secret/path")

    app.dependency_overrides[get_storage] = broken_storage
    response = upload(client, make_csv())
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "boom" not in response.text and "/secret/path" not in response.text
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nothing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --- filenames ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("data.csv", "data.csv"),
        ("../../etc/evil.csv", "evil.csv"),
        ("C:\\Users\\me\\sales.csv", "sales.csv"),
        ("bad\x00name\n.csv", "badname.csv"),
        ("", "upload.csv"),
        (None, "upload.csv"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_stored_name_comes_from_ids_not_the_filename(client: TestClient, tmp_path: Path) -> None:
    body = upload(client, make_csv(), filename="../../evil.csv").json()
    assert body["original_filename"] == "evil.csv"
    (stored,) = stored_files(tmp_path)
    assert stored.name == "source.csv"
    assert body["dataset_id"] in stored.parts


# --- the register-then-upload flow --------------------------------------------------------------


def register(client: TestClient, size: int = 100, filename: str = "data.csv") -> dict:
    response = client.post("/api/v1/datasets", json={"filename": filename, "size_bytes": size})
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_registering_returns_a_target_on_this_api_in_local_mode(
    client: TestClient, tmp_path: Path
) -> None:
    body = register(client)
    assert body["status"] == "PENDING_UPLOAD" and body["size_bytes"] == 100
    assert body["upload"] == {
        "method": "PUT",
        "url": f"/api/v1/datasets/{body['dataset_id']}/content",
        "headers": {"Content-Type": "text/csv"},
        "expires_in_seconds": None,
        "requires_auth": True,
    }
    assert stored_files(tmp_path) == []  # nothing is stored until the bytes arrive


def test_validating_before_the_file_arrives_is_a_conflict_not_a_rejection(
    client: TestClient,
) -> None:
    dataset_id = register(client)["dataset_id"]
    response = client.post(f"/api/v1/datasets/{dataset_id}/validate")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"
    assert client.get(f"/api/v1/datasets/{dataset_id}").json()["status"] == "PENDING_UPLOAD"


def test_the_declared_size_must_match_the_upload(client: TestClient, tmp_path: Path) -> None:
    csv = make_csv()
    too_small = register(client, size=len(csv) + 50)["upload"]["url"]
    short = client.put(too_small, content=csv)
    assert short.status_code == 422
    assert short.json()["error"]["details"] == [{"field": "body", "issue": "size_mismatch"}]

    too_big = register(client, size=len(csv) - 10)["upload"]["url"]
    long = client.put(too_big, content=csv)
    assert long.status_code == 413
    assert stored_files(tmp_path) == []  # neither upload left a file behind


def test_content_can_only_be_sent_while_the_dataset_is_waiting_for_it(client: TestClient) -> None:
    csv = make_csv()
    body = register(client, size=len(csv))
    url = body["upload"]["url"]
    assert client.put(url, content=csv).status_code == 204
    assert client.put(url, content=csv).status_code == 204  # may be retried until validated
    client.post(f"/api/v1/datasets/{body['dataset_id']}/validate")
    again = client.put(url, content=csv)
    assert again.status_code == 409
    assert client.put("/api/v1/datasets/ds_missing/content", content=csv).status_code == 404


def test_only_the_owner_can_send_content(app: FastAPI, client: TestClient) -> None:
    csv = make_csv()
    body = register(client, size=len(csv))
    app.dependency_overrides[get_owner_id] = lambda: "someone-else"
    assert client.put(body["upload"]["url"], content=csv).status_code == 404


def test_a_size_that_differs_from_the_declaration_is_caught_at_validation(
    client: TestClient, storage: LocalStorage, alice: TestUser
) -> None:
    """With S3 the size is pinned by the signed URL, but validation checks it independently."""
    body = register(client, size=500)
    key = f"datasets/{alice.user_id}/{body['dataset_id']}/source.csv"
    storage.save(key, io.BytesIO(make_csv()), 10_000)  # not 500 bytes
    report = client.post(f"/api/v1/datasets/{body['dataset_id']}/validate").json()
    assert report["status"] == "REJECTED"
    assert "declared size" in report["message"]
    assert not storage.exists(key)


def test_datasets_created_before_the_upload_flow_still_validate(
    client: TestClient,
    storage: LocalStorage,
    alice: TestUser,
    session_factory: sessionmaker[Session],
) -> None:
    """Rows from before M6 have status UPLOADED and their file already stored."""
    csv = make_csv()
    key = f"datasets/{alice.user_id}/ds_legacy/source.csv"
    storage.save(key, io.BytesIO(csv), 10_000)
    with session_factory() as session:
        create_dataset(
            session,
            dataset_id="ds_legacy",
            owner_id=alice.user_id,
            storage_key=key,
            original_filename="old.csv",
            size_bytes=len(csv),
            status="UPLOADED",
        )
    assert client.post("/api/v1/datasets/ds_legacy/validate").json()["status"] == "READY"
