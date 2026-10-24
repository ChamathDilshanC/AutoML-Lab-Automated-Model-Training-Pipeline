"""Dataset and target-column validation.

Error messages may mention column names and counts but never cell values, so they are safe to
show to users (docs/SECURITY.md).
"""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from automl.tasks import TASKS


class DataValidationError(ValueError):
    """Raised when a dataset or experiment configuration is not usable."""


@dataclass(frozen=True)
class ValidationLimits:
    """Dataset size limits.

    The defaults are proposed starting points; the real values are an open decision
    (docs/PRD.md, NFR-005).
    """

    min_rows: int = 10
    min_columns: int = 2
    max_rows: int = 1_000_000
    max_columns: int = 1_000


def validate_headers(columns: Sequence[object]) -> None:
    """Reject empty, duplicate or ambiguous column names.

    Names that differ only by case or surrounding whitespace count as duplicates. A CSV reader
    renames repeated headers (`a`, `a.1`), so call this on the raw header row as well.
    """
    names = [str(column) for column in columns]
    blank = [position for position, name in enumerate(names) if not name.strip()]
    if blank:
        raise DataValidationError(f"Column name is empty at position(s): {blank}.")

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for name in names:
        key = name.strip().casefold()
        if key in seen:
            duplicates.append(name)
        else:
            seen[key] = name
    if duplicates:
        raise DataValidationError(
            f"Duplicate or ambiguous column names: {sorted(set(duplicates))}."
        )


def validate_dataframe(df: pd.DataFrame, limits: ValidationLimits | None = None) -> None:
    """Check that a loaded dataset is non-empty, within limits and has unambiguous headers."""
    limits = limits or ValidationLimits()
    if not isinstance(df, pd.DataFrame):
        raise DataValidationError("Dataset must be a table.")
    validate_headers(list(df.columns))

    n_rows, n_columns = df.shape
    if n_rows == 0:
        raise DataValidationError("Dataset has no rows.")
    if n_rows < limits.min_rows:
        raise DataValidationError(
            f"Dataset has {n_rows} rows; at least {limits.min_rows} are required."
        )
    if n_rows > limits.max_rows:
        raise DataValidationError(f"Dataset has {n_rows} rows; the limit is {limits.max_rows}.")
    if n_columns < limits.min_columns:
        raise DataValidationError(
            f"Dataset has {n_columns} column(s); at least {limits.min_columns} are required."
        )
    if n_columns > limits.max_columns:
        raise DataValidationError(
            f"Dataset has {n_columns} columns; the limit is {limits.max_columns}."
        )


def validate_target(df: pd.DataFrame, target: str, task: str) -> None:
    """Check that the target column can be used for the given task.

    Requirements: the task is supported, the column exists, has no missing values and more than
    one distinct value. Regression targets must be numeric. For classification every class needs
    at least two rows, which stratified splitting and cross-validation rely on.
    """
    if task not in TASKS:
        raise DataValidationError(f"Unsupported task {task!r}; expected one of {list(TASKS)}.")
    validate_headers(list(df.columns))
    if target not in df.columns:
        raise DataValidationError(f"Target column {target!r} is not in this dataset.")

    series = df[target]
    missing = int(series.isna().sum())
    if missing:
        raise DataValidationError(f"Target column {target!r} has {missing} missing value(s).")
    if series.nunique() < 2:
        raise DataValidationError(f"Target column {target!r} has fewer than two distinct values.")

    if task == "regression":
        if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
            raise DataValidationError(f"Target column {target!r} must be numeric for regression.")
    else:
        too_small = int((series.value_counts() < 2).sum())
        if too_small:
            raise DataValidationError(
                f"{too_small} class(es) in target column {target!r} have fewer than 2 rows."
            )
