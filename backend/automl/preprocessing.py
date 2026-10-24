"""Preprocessing pipelines.

`build_preprocessor` returns an *unfitted* transformer. It is meant to be the first step of a
scikit-learn `Pipeline`, so imputers, scalers and encoders are fitted on training data only
(and, during cross-validation, on each training fold only).
"""

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_STRATEGIES = ("mean", "median")


def split_column_types(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return (numeric columns, categorical columns). Booleans are treated as categorical."""
    numeric = [
        column
        for column in X.columns
        if pd.api.types.is_numeric_dtype(X[column]) and not pd.api.types.is_bool_dtype(X[column])
    ]
    categorical = [column for column in X.columns if column not in numeric]
    return numeric, categorical


def build_preprocessor(X: pd.DataFrame, numeric_strategy: str = "median") -> ColumnTransformer:
    """Build an unfitted `ColumnTransformer` for the columns of `X`.

    Numeric columns: imputation (`mean` or `median`) then standard scaling.
    Categorical columns: most-frequent imputation then one-hot encoding that ignores unseen
    categories at prediction time.
    """
    if numeric_strategy not in NUMERIC_STRATEGIES:
        raise ValueError(f"numeric_strategy must be one of {list(NUMERIC_STRATEGIES)}.")

    numeric, categorical = split_column_types(X)
    transformers = []
    if numeric:
        numeric_pipeline = Pipeline(
            [
                ("impute", SimpleImputer(strategy=numeric_strategy)),
                ("scale", StandardScaler()),
            ]
        )
        transformers.append(("num", numeric_pipeline, numeric))
    if categorical:
        categorical_pipeline = Pipeline(
            [
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("encode", OneHotEncoder(handle_unknown="ignore")),
            ]
        )
        transformers.append(("cat", categorical_pipeline, categorical))
    if not transformers:
        raise ValueError("No feature columns to preprocess.")
    return ColumnTransformer(transformers, remainder="drop")
