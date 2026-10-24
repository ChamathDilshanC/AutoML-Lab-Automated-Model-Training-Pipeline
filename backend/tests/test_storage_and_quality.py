import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.storage import FileTooLargeError, LocalStorage, StorageError
from automl.quality import quality_warnings, summarize_schema
from automl.validation import DataValidationError, read_csv_bytes

# --- local storage ------------------------------------------------------------------------------


def test_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    assert storage.save("datasets/u/d/source.csv", io.BytesIO(b"a,b\n1,2\n"), 100) == 8
    assert storage.exists("datasets/u/d/source.csv")
    assert storage.read("datasets/u/d/source.csv") == b"a,b\n1,2\n"
    storage.delete("datasets/u/d/source.csv")
    assert not storage.exists("datasets/u/d/source.csv")
    storage.delete("datasets/u/d/source.csv")  # deleting twice is fine


@pytest.mark.parametrize("key", ["../outside.csv", "a/../../outside.csv", "/etc/passwd"])
def test_storage_rejects_keys_outside_the_root(tmp_path: Path, key: str) -> None:
    storage = LocalStorage(tmp_path / "root")
    with pytest.raises(StorageError):
        storage.save(key, io.BytesIO(b"x"), 100)
    with pytest.raises(StorageError):
        storage.read(key)


def test_storage_size_limit_leaves_no_files(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    with pytest.raises(FileTooLargeError):
        storage.save("d/source.csv", io.BytesIO(b"x" * 50), 10)
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


# --- CSV loading --------------------------------------------------------------------------------


def csv_bytes(rows: int = 12, header: str = "a,b") -> bytes:
    return (header + "\n" + "\n".join(f"{i},{i * 2}" for i in range(rows)) + "\n").encode()


def test_read_csv_bytes_handles_a_utf8_bom() -> None:
    df = read_csv_bytes(b"\xef\xbb\xbf" + csv_bytes())
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 12


def test_read_csv_bytes_rejects_raw_duplicate_headers() -> None:
    with pytest.raises(DataValidationError, match="Duplicate"):
        read_csv_bytes(csv_bytes(header="a,A"))


def test_read_csv_bytes_rejects_inconsistent_rows_instead_of_guessing_an_index() -> None:
    ragged = b"a,b\n" + b"1,2,3\n" * 12
    with pytest.raises(DataValidationError, match="same number of fields"):
        read_csv_bytes(ragged)


def test_read_csv_bytes_ignores_blank_lines() -> None:
    assert len(read_csv_bytes(csv_bytes() + b"\n\n")) == 12


# --- schema summary and warnings ----------------------------------------------------------------


def clean_frame(n: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "x": rng.normal(size=n),
            "group": rng.choice(["a", "b", "c"], size=n),
            "count": rng.integers(0, 5, size=n),
        }
    )


def test_schema_summary_reports_types_missing_and_uniques() -> None:
    df = clean_frame(40)
    df.loc[:9, "x"] = np.nan
    by_name = {c.name: c for c in summarize_schema(df)}
    assert by_name["x"].kind == "numeric"
    assert by_name["x"].missing_count == 10
    assert by_name["x"].missing_percent == 25.0
    assert by_name["group"].kind == "categorical"
    assert by_name["group"].unique_count == 3


def test_clean_data_has_no_warnings() -> None:
    assert quality_warnings(clean_frame()) == []


def test_warnings_flag_common_problems() -> None:
    df = clean_frame(40)
    df["constant"] = 1
    df["row_id"] = range(40)
    df["mostly_empty"] = np.where(np.arange(40) < 30, np.nan, np.arange(40) / 2)
    found = {w.code: w for w in quality_warnings(df)}
    assert {"tiny_dataset", "constant_column", "identifier_like", "high_missing"} <= set(found)
    assert found["constant_column"].columns == ["constant"]
    assert found["identifier_like"].columns == ["row_id"]
    assert found["high_missing"].columns == ["mostly_empty"]


def test_duplicate_rows_are_flagged() -> None:
    df = clean_frame(100)
    df = pd.concat([df, df.head(3)], ignore_index=True)
    found = {w.code: w for w in quality_warnings(df)}
    assert found["duplicate_rows"].severity == "info"
    assert "3 duplicate" in found["duplicate_rows"].message


def test_high_cardinality_categories_are_flagged() -> None:
    df = clean_frame(200)
    df["code"] = [f"c{i % 80}" for i in range(200)]
    found = {w.code: w for w in quality_warnings(df)}
    assert found["high_cardinality"].columns == ["code"]
    assert "identifier_like" not in found


def test_warnings_never_contain_cell_values() -> None:
    df = clean_frame(40)
    df["token"] = [f"SECRET_{i}" for i in range(40)]
    text = " ".join(w.message for w in quality_warnings(df))
    assert "SECRET_" not in text
