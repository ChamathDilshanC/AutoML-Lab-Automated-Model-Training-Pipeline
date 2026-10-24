"""Deterministic tests for the AutoML engine (docs/TESTING_STRATEGY.md, ML layer)."""

from typing import Any

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GridSearchCV

from automl import trainer
from automl.evaluator import (
    DEFAULT_METRIC,
    METRICS,
    evaluate,
    get_metric,
    rank_results,
    scoring_for,
)
from automl.preprocessing import build_preprocessor, split_column_types
from automl.splits import separate_target, split_data
from automl.trainer import available_algorithms, train_model
from automl.validation import (
    DataValidationError,
    ValidationLimits,
    validate_dataframe,
    validate_headers,
    validate_target,
)

# --- fixtures -----------------------------------------------------------------------------------


@pytest.fixture
def classification_df() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 90
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    color = rng.choice(["red", "green", "blue"], size=n)
    label = np.where(x1 + 0.3 * x2 + rng.normal(scale=0.3, size=n) > 0, "pos", "neg")
    df = pd.DataFrame({"x1": x1, "x2": x2, "color": color, "label": label})
    df.loc[[3, 17], "x2"] = np.nan
    df.loc[[5], "color"] = None
    return df


@pytest.fixture
def regression_df() -> pd.DataFrame:
    rng = np.random.default_rng(1)
    n = 90
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    group = rng.choice(["a", "b"], size=n)
    price = 3 * x1 - 2 * x2 + np.where(group == "a", 1.0, -1.0) + rng.normal(scale=0.1, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "group": group, "price": price})


class FakeClassifier:
    """Returns fixed predictions so metric values can be checked exactly."""

    classes_ = np.array([0, 1])

    def predict(self, X: Any) -> np.ndarray:
        return np.array([0, 1, 1, 1])

    def predict_proba(self, X: Any) -> np.ndarray:
        return np.array([[0.9, 0.1], [0.4, 0.6], [0.2, 0.8], [0.1, 0.9]])


class FakeRegressor:
    def predict(self, X: Any) -> np.ndarray:
        return np.array([1.0, 2.0, 3.0, 6.0])


# --- validation ---------------------------------------------------------------------------------


def test_valid_dataset_and_target_pass(classification_df: pd.DataFrame) -> None:
    validate_dataframe(classification_df)
    validate_target(classification_df, "label", "classification")


def test_empty_dataset_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="no rows"):
        validate_dataframe(pd.DataFrame({"a": [], "b": []}))


def test_too_few_rows_or_columns_are_rejected() -> None:
    with pytest.raises(DataValidationError, match="rows"):
        validate_dataframe(pd.DataFrame({"a": [1, 2], "b": [3, 4]}))
    with pytest.raises(DataValidationError, match="column"):
        validate_dataframe(pd.DataFrame({"a": range(20)}))


def test_limits_are_configurable() -> None:
    df = pd.DataFrame({"a": range(20), "b": range(20)})
    with pytest.raises(DataValidationError, match="limit"):
        validate_dataframe(df, ValidationLimits(max_rows=5))
    with pytest.raises(DataValidationError, match="limit"):
        validate_dataframe(df, ValidationLimits(max_columns=1))


def test_duplicate_and_ambiguous_headers_are_rejected() -> None:
    with pytest.raises(DataValidationError, match="Duplicate"):
        validate_headers(["a", "b", "a"])
    with pytest.raises(DataValidationError, match="Duplicate"):
        validate_headers(["Price", " price "])
    duplicated = pd.DataFrame([[1, 2]] * 12, columns=["a", "a"])
    with pytest.raises(DataValidationError, match="Duplicate"):
        validate_dataframe(duplicated)


def test_empty_column_name_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="empty"):
        validate_headers(["a", " "])


def test_target_must_exist(classification_df: pd.DataFrame) -> None:
    with pytest.raises(DataValidationError, match="not in this dataset"):
        validate_target(classification_df, "missing", "classification")


def test_target_needs_more_than_one_distinct_value() -> None:
    df = pd.DataFrame({"x": range(12), "y": [1] * 12})
    with pytest.raises(DataValidationError, match="fewer than two"):
        validate_target(df, "y", "classification")


def test_target_with_missing_values_is_rejected(classification_df: pd.DataFrame) -> None:
    classification_df.loc[0, "label"] = None
    with pytest.raises(DataValidationError, match="missing"):
        validate_target(classification_df, "label", "classification")


def test_regression_target_must_be_numeric(classification_df: pd.DataFrame) -> None:
    with pytest.raises(DataValidationError, match="numeric"):
        validate_target(classification_df, "label", "regression")


def test_classification_classes_need_two_rows() -> None:
    df = pd.DataFrame({"x": range(12), "y": ["a"] * 11 + ["b"]})
    with pytest.raises(DataValidationError, match="fewer than 2 rows"):
        validate_target(df, "y", "classification")


def test_unsupported_task_is_rejected(classification_df: pd.DataFrame) -> None:
    with pytest.raises(DataValidationError, match="Unsupported task"):
        validate_target(classification_df, "label", "clustering")


def test_error_messages_do_not_leak_cell_values() -> None:
    df = pd.DataFrame({"x": range(12), "y": ["SECRET_VALUE"] * 11 + ["OTHER_SECRET"]})
    with pytest.raises(DataValidationError) as excinfo:
        validate_target(df, "y", "classification")
    assert "SECRET_VALUE" not in str(excinfo.value)
    assert "OTHER_SECRET" not in str(excinfo.value)


# --- preprocessing ------------------------------------------------------------------------------


def test_column_types_are_separated(classification_df: pd.DataFrame) -> None:
    X, _ = separate_target(classification_df, "label")
    numeric, categorical = split_column_types(X)
    assert numeric == ["x1", "x2"]
    assert categorical == ["color"]


def test_preprocessor_imputes_scales_and_encodes(classification_df: pd.DataFrame) -> None:
    X, _ = separate_target(classification_df, "label")
    transformed = build_preprocessor(X).fit_transform(X)
    dense = transformed.toarray() if hasattr(transformed, "toarray") else transformed
    assert not np.isnan(dense).any()
    assert dense.shape == (len(X), 2 + 3)  # two numeric + three colours


def test_preprocessor_ignores_unseen_categories(classification_df: pd.DataFrame) -> None:
    X, _ = separate_target(classification_df, "label")
    preprocessor = build_preprocessor(X).fit(X)
    unseen = X.head(2).copy()
    unseen["color"] = "purple"
    assert preprocessor.transform(unseen).shape[0] == 2


def test_preprocessor_is_fitted_on_training_data_only(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification")
    preprocessor = build_preprocessor(split.X_train).fit(split.X_train)
    scaler = preprocessor.named_transformers_["num"].named_steps["scale"]
    imputer = preprocessor.named_transformers_["num"].named_steps["impute"]
    train_median = split.X_train[["x1", "x2"]].median().to_numpy()
    full_median = X[["x1", "x2"]].median().to_numpy()
    assert np.allclose(imputer.statistics_, train_median)
    assert not np.allclose(train_median, full_median)
    imputed = imputer.transform(split.X_train[["x1", "x2"]])
    assert np.allclose(scaler.mean_, imputed.mean(axis=0))


def test_invalid_numeric_strategy_is_rejected(classification_df: pd.DataFrame) -> None:
    X, _ = separate_target(classification_df, "label")
    with pytest.raises(ValueError, match="numeric_strategy"):
        build_preprocessor(X, numeric_strategy="mode")


# --- splits -------------------------------------------------------------------------------------


def test_target_is_not_in_features(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    assert "label" not in X.columns
    assert y.name == "label"
    assert list(X.columns) == ["x1", "x2", "color"]


def test_split_has_no_overlap_and_covers_all_rows(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification", test_size=0.2)
    assert set(split.X_train.index).isdisjoint(split.X_test.index)
    assert len(split.X_train) + len(split.X_test) == len(X)
    assert len(split.X_test) == pytest.approx(0.2 * len(X), abs=1)
    assert split.strategy == "stratified_random"


def test_classification_split_is_stratified(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification")
    overall = y.value_counts(normalize=True)
    for part in (split.y_train, split.y_test):
        shares = part.value_counts(normalize=True)
        for label in overall.index:
            assert shares[label] == pytest.approx(overall[label], abs=0.05)


def test_regression_split_is_not_stratified(regression_df: pd.DataFrame) -> None:
    X, y = separate_target(regression_df, "price")
    split = split_data(X, y, "regression")
    assert split.strategy == "random"


def test_split_is_reproducible_for_the_same_seed(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    first = split_data(X, y, "classification", random_state=7)
    second = split_data(X, y, "classification", random_state=7)
    other = split_data(X, y, "classification", random_state=8)
    assert list(first.X_test.index) == list(second.X_test.index)
    assert list(first.X_test.index) != list(other.X_test.index)
    assert first.random_state == 7


def test_invalid_split_arguments_are_rejected(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    with pytest.raises(ValueError, match="test_size"):
        split_data(X, y, "classification", test_size=1.5)
    with pytest.raises(ValueError, match="same number"):
        split_data(X, y.head(5), "classification")


def test_tiny_dataset_gives_a_safe_error() -> None:
    X = pd.DataFrame({"x": range(4)})
    y = pd.Series(["a", "a", "b", "b"])
    with pytest.raises(DataValidationError, match="too small"):
        split_data(X, y, "classification", test_size=0.2)


# --- trainer ------------------------------------------------------------------------------------


def test_algorithm_allowlist() -> None:
    assert available_algorithms("classification") == [
        "decision_tree",
        "logistic_regression",
        "random_forest",
    ]
    assert available_algorithms("regression") == [
        "decision_tree",
        "linear_regression",
        "random_forest",
    ]


def test_unknown_algorithm_is_rejected(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    with pytest.raises(ValueError, match="Unsupported algorithm"):
        train_model(X, y, "classification", "os.system")
    with pytest.raises(ValueError, match="Unsupported algorithm"):
        train_model(X, y, "classification", "linear_regression")


@pytest.mark.parametrize("algorithm", available_algorithms("classification"))
def test_every_classifier_trains_and_predicts(
    classification_df: pd.DataFrame, algorithm: str
) -> None:
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification")
    model = train_model(split.X_train, split.y_train, "classification", algorithm)
    metrics = evaluate(model.pipeline, split.X_test, split.y_test, "classification")
    assert metrics["accuracy"] is not None and metrics["accuracy"] >= 0.75
    assert model.cv_score is not None and model.cv_folds == 3


@pytest.mark.parametrize("algorithm", available_algorithms("regression"))
def test_every_regressor_trains_and_predicts(regression_df: pd.DataFrame, algorithm: str) -> None:
    X, y = separate_target(regression_df, "price")
    split = split_data(X, y, "regression")
    model = train_model(split.X_train, split.y_train, "regression", algorithm)
    metrics = evaluate(model.pipeline, split.X_test, split.y_test, "regression")
    assert metrics["r2"] is not None and metrics["r2"] > 0.5


def test_hyperparameter_search_sees_only_training_rows(
    classification_df: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []

    class SpySearch(GridSearchCV):
        def fit(self, X: Any, y: Any = None, **params: Any) -> Any:
            seen.append(len(X))
            return super().fit(X, y, **params)

    monkeypatch.setattr(trainer, "GridSearchCV", SpySearch)
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification")
    train_model(split.X_train, split.y_train, "classification", "decision_tree")
    assert seen == [len(split.X_train)]
    assert len(split.X_train) < len(classification_df)


def test_training_is_reproducible(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification", random_state=3)
    runs = [
        train_model(split.X_train, split.y_train, "classification", "random_forest", random_state=3)
        for _ in range(2)
    ]
    assert runs[0].best_params == runs[1].best_params
    assert runs[0].cv_score == runs[1].cv_score
    metrics = [evaluate(run.pipeline, split.X_test, split.y_test, "classification") for run in runs]
    assert metrics[0] == metrics[1]


def test_trained_model_records_its_configuration(classification_df: pd.DataFrame) -> None:
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification")
    model = train_model(split.X_train, split.y_train, "classification", "logistic_regression")
    assert model.feature_names == ["x1", "x2", "color"]
    assert "label" not in model.feature_names
    assert model.tuning_metric == DEFAULT_METRIC["classification"]
    assert model.random_state == 42
    assert {"python", "numpy", "pandas", "scikit-learn"} <= set(model.library_versions)
    assert set(model.best_params) == {"C"}


def test_regression_cv_score_uses_natural_units(regression_df: pd.DataFrame) -> None:
    X, y = separate_target(regression_df, "price")
    split = split_data(X, y, "regression")
    model = train_model(split.X_train, split.y_train, "regression", "decision_tree", metric="rmse")
    assert model.cv_score is not None and model.cv_score > 0  # RMSE, lower is better


def test_linear_regression_has_nothing_to_tune(regression_df: pd.DataFrame) -> None:
    X, y = separate_target(regression_df, "price")
    split = split_data(X, y, "regression")
    model = train_model(split.X_train, split.y_train, "regression", "linear_regression")
    assert model.best_params == {}
    assert model.cv_score is None and model.cv_folds is None


# --- evaluator ----------------------------------------------------------------------------------


def test_classification_metrics_have_expected_values() -> None:
    y_true = pd.Series([0, 0, 1, 1])
    metrics = evaluate(FakeClassifier(), pd.DataFrame({"x": range(4)}), y_true, "classification")
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["precision"] == pytest.approx(5 / 6)
    assert metrics["recall"] == pytest.approx(0.75)
    assert metrics["f1"] == pytest.approx((2 / 3 + 0.8) / 2)
    assert metrics["roc_auc"] == pytest.approx(1.0)


def test_regression_metrics_have_expected_values() -> None:
    y_true = pd.Series([1.0, 2.0, 3.0, 4.0])
    metrics = evaluate(FakeRegressor(), pd.DataFrame({"x": range(4)}), y_true, "regression")
    assert metrics["mae"] == pytest.approx(0.5)
    assert metrics["rmse"] == pytest.approx(1.0)
    assert metrics["r2"] == pytest.approx(0.2)


def test_roc_auc_is_none_when_not_computable() -> None:
    class NoProba:
        def predict(self, X: Any) -> np.ndarray:
            return np.array([0, 1, 1, 1])

    X = pd.DataFrame({"x": range(4)})
    assert evaluate(NoProba(), X, pd.Series([0, 0, 1, 1]), "classification")["roc_auc"] is None
    single_class = evaluate(FakeClassifier(), X, pd.Series([1, 1, 1, 1]), "classification")
    assert single_class["roc_auc"] is None


def test_metric_directions() -> None:
    assert not get_metric("regression", "mae").higher_is_better
    assert not get_metric("regression", "rmse").higher_is_better
    assert get_metric("regression", "r2").higher_is_better
    assert all(spec.higher_is_better for spec in METRICS["classification"].values())


def test_unknown_or_wrong_task_metric_is_rejected() -> None:
    with pytest.raises(ValueError, match="not available"):
        get_metric("classification", "rmse")
    with pytest.raises(ValueError, match="not available"):
        get_metric("regression", "f1")


def test_roc_auc_scoring_depends_on_class_count() -> None:
    assert scoring_for("classification", "roc_auc", 2) == "roc_auc"
    assert scoring_for("classification", "roc_auc", 3) == "roc_auc_ovr_weighted"


def test_ranking_respects_direction_and_excludes_failed_runs() -> None:
    higher = {
        "a": {"f1": 0.7},
        "b": {"f1": 0.9},
        "c": {"f1": None},
        "d": {"f1": float("nan")},
    }
    assert rank_results(higher, "classification", "f1") == ["b", "a"]
    lower = {"a": {"rmse": 2.0}, "b": {"rmse": 1.0}, "c": {}}
    assert rank_results(lower, "regression", "rmse") == ["b", "a"]


def test_ranking_ties_are_broken_by_name() -> None:
    results = {"zeta": {"r2": 0.5}, "alpha": {"r2": 0.5}}
    assert rank_results(results, "regression", "r2") == ["alpha", "zeta"]


# --- end to end ---------------------------------------------------------------------------------


def test_end_to_end_classification_workflow(classification_df: pd.DataFrame) -> None:
    validate_dataframe(classification_df)
    validate_target(classification_df, "label", "classification")
    X, y = separate_target(classification_df, "label")
    split = split_data(X, y, "classification")
    results = {}
    for algorithm in available_algorithms("classification"):
        model = train_model(split.X_train, split.y_train, "classification", algorithm)
        results[algorithm] = evaluate(model.pipeline, split.X_test, split.y_test, "classification")
    ranking = rank_results(results, "classification", "f1")
    assert sorted(ranking) == available_algorithms("classification")
    assert results[ranking[0]]["f1"] >= results[ranking[-1]]["f1"]  # type: ignore[operator]
