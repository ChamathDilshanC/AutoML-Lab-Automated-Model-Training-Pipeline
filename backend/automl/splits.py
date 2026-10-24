"""Train/test splitting."""

from dataclasses import dataclass

import pandas as pd
from sklearn.model_selection import train_test_split

from automl.tasks import Task
from automl.validation import DataValidationError


@dataclass(frozen=True)
class DataSplit:
    """A train/test split plus the settings that produced it (recorded for reproducibility)."""

    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    strategy: str
    test_size: float
    random_state: int


def separate_target(df: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series]:
    """Split a dataset into features and target. The target is never part of the features."""
    if target not in df.columns:
        raise DataValidationError(f"Target column {target!r} is not in this dataset.")
    return df.drop(columns=[target]), df[target]


def split_data(
    X: pd.DataFrame,
    y: pd.Series,
    task: Task,
    test_size: float = 0.2,
    random_state: int = 42,
) -> DataSplit:
    """Randomly split into train and held-out test sets; stratified for classification."""
    if not 0 < test_size < 1:
        raise ValueError("test_size must be between 0 and 1 (exclusive).")
    if len(X) != len(y):
        raise ValueError("X and y must have the same number of rows.")

    stratify = y if task == "classification" else None
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=stratify
        )
    except ValueError as exc:
        raise DataValidationError(
            "Dataset is too small to split with the requested test size."
        ) from exc

    return DataSplit(
        X_train=X_train,
        X_test=X_test,
        y_train=y_train,
        y_test=y_test,
        strategy="stratified_random" if stratify is not None else "random",
        test_size=test_size,
        random_state=random_state,
    )
