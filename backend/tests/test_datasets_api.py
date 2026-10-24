"""API tests for the dataset workflow (upload, validate, read)."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_storage
from app.core.security import get_owner_id
from app.services.datasets import sanitize_filename


def make_csv(rows: int = 30) -> bytes:
    lines = ["age,income,city,bought"]
    for i in range(rows):
        lines.append(f"{20 + i},{30000 + 500 * i},{('Paris', 'Rome', 'Oslo')[i % 3]},{i % 2}")
    return ("\n".join(lines) + "\n").encode()


def upload(client: TestClient, content: bytes, filename: str = "data.csv"):
    return client.post("/api/v1/datasets", files={"file": (filename, content, "text/csv")})


def stored_files(tmp_path: Path) -> list[Path]:
    return [p for p in (tmp_path / "storage").rglob("*") if p.is_file()]


# --- happy path ---------------------------------------------------------------------------------


def test_upload_validate_and_read(client: TestClient, tmp_path: Path) -> None:
    created = upload(client, make_csv())
    assert created.status_code == 201
    assert created.headers["X-Request-ID"].startswith("req_")
    body = created.json()
    assert body["status"] == "UPLOADED"
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


def test_missing_file_field_uses_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/datasets")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "file"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_file_over_the_limit_is_rejected_and_not_kept(client: TestClient, tmp_path: Path) -> None:
    response = upload(
        client, b"a,b\n" + b"1,2\n" * 6000
    )  # ~24 kB: over the limit, under the body cap
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert stored_files(tmp_path) == []


def test_huge_request_is_rejected_by_content_length(client: TestClient) -> None:
    response = upload(client, b"x" * 200_000)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


# --- malformed files are REJECTED with safe messages --------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", "empty"),
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
    dataset_id = upload(client, b"").json()["dataset_id"]
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
