"""Schema summary and data-quality warnings for a loaded dataset.

Output contains column names and counts only, never cell values.
"""

from dataclasses import dataclass

import pandas as pd

from automl.preprocessing import split_column_types

# Proposed thresholds; tune once real datasets have been profiled.
TINY_DATASET_ROWS = 50
HIGH_MISSING_SHARE = 0.5
HIGH_CARDINALITY_UNIQUE = 50


@dataclass(frozen=True)
class ColumnSummary:
    name: str
    kind: str  # "numeric" or "categorical"
    missing_count: int
    missing_percent: float
    unique_count: int


@dataclass(frozen=True)
class QualityWarning:
    code: str
    severity: str  # "info" or "warning"
    message: str
    columns: list[str]


def summarize_schema(df: pd.DataFrame) -> list[ColumnSummary]:
    numeric, _ = split_column_types(df)
    n_rows = len(df)
    summaries = []
    for column in df.columns:
        missing = int(df[column].isna().sum())
        summaries.append(
            ColumnSummary(
                name=str(column),
                kind="numeric" if column in numeric else "categorical",
                missing_count=missing,
                missing_percent=round(100 * missing / n_rows, 1) if n_rows else 0.0,
                unique_count=int(df[column].nunique()),
            )
        )
    return summaries


def quality_warnings(df: pd.DataFrame) -> list[QualityWarning]:
    """Flag common data problems: tiny data, constant, mostly-empty, identifier-like columns."""
    n_rows = len(df)
    numeric, _ = split_column_types(df)
    warnings: list[QualityWarning] = []

    if n_rows < TINY_DATASET_ROWS:
        warnings.append(
            QualityWarning(
                "tiny_dataset",
                "warning",
                f"Only {n_rows} rows; results from so little data are unreliable.",
                [],
            )
        )

    constant = [str(c) for c in df.columns if df[c].nunique() <= 1]
    if constant:
        warnings.append(
            QualityWarning(
                "constant_column",
                "warning",
                "Columns with a single value carry no signal.",
                constant,
            )
        )

    mostly_missing = [str(c) for c in df.columns if df[c].isna().mean() >= HIGH_MISSING_SHARE]
    if mostly_missing:
        warnings.append(
            QualityWarning(
                "high_missing",
                "warning",
                f"At least {int(HIGH_MISSING_SHARE * 100)}% of values are missing.",
                mostly_missing,
            )
        )

    identifiers = [
        str(c)
        for c in df.columns
        if n_rows > 1
        and df[c].nunique() == n_rows
        and (c not in numeric or pd.api.types.is_integer_dtype(df[c]))
    ]
    if identifiers:
        warnings.append(
            QualityWarning(
                "identifier_like",
                "warning",
                "Every row has a different value; this looks like an identifier and can cause "
                "leakage or overfitting.",
                identifiers,
            )
        )

    high_cardinality = [
        str(c)
        for c in df.columns
        if c not in numeric
        and str(c) not in identifiers
        and df[c].nunique() > HIGH_CARDINALITY_UNIQUE
    ]
    if high_cardinality:
        warnings.append(
            QualityWarning(
                "high_cardinality",
                "warning",
                f"More than {HIGH_CARDINALITY_UNIQUE} distinct categories; one-hot encoding will "
                "create many columns.",
                high_cardinality,
            )
        )

    duplicates = int(df.duplicated().sum())
    if duplicates:
        warnings.append(
            QualityWarning("duplicate_rows", "info", f"{duplicates} duplicate row(s) found.", [])
        )

    return warnings
