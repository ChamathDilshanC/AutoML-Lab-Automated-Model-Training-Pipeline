"""Engine-level tests for model artifacts and strict prediction-input validation."""

import numpy as np
import pandas as pd
import pytest

from automl.registry import (
    MAX_CATEGORIES,
    MAX_REPORTED_ISSUES,
    MAX_STRING_LENGTH,
    InstanceValidationError,
    build_feature_schema,
    build_metadata,
    dumps_pipeline,
    instances_to_frame,
    jsonable_values,
    loads_pipeline,
    sha256_hex,
)
from automl.splits import separate_target, split_data
from automl.trainer import train_model


def training_frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 60
    return pd.DataFrame(
        {
            "age": rng.integers(18, 70, size=n).astype(float),
            "city": rng.choice(["Paris", "Rome", "Oslo"], size=n),
            "member": rng.choice([True, False], size=n),
            "target": rng.choice(["yes", "no"], size=n),
        }
    )


# --- feature schema -----------------------------------------------------------------------------


def test_feature_schema_describes_each_input_column() -> None:
    X, _ = separate_target(training_frame(), "target")
    schema = {spec["name"]: spec for spec in build_feature_schema(X)}
    assert list(schema) == ["age", "city", "member"]
    assert schema["age"] == {
        "name": "age",
        "kind": "numeric",
        "value_type": "number",
        "categories": None,
    }
    assert schema["city"]["value_type"] == "string"
    assert schema["city"]["categories"] == ["Oslo", "Paris", "Rome"]
    assert schema["member"]["value_type"] == "boolean"
    assert "target" not in schema


def test_high_cardinality_columns_do_not_list_their_values() -> None:
    X = pd.DataFrame({"code": [f"c{i}" for i in range(MAX_CATEGORIES + 5)]})
    (spec,) = build_feature_schema(X)
    assert spec["value_type"] == "string" and spec["categories"] is None


# --- artifacts ----------------------------------------------------------------------------------


def test_pipeline_round_trips_through_bytes() -> None:
    X, y = separate_target(training_frame(), "target")
    split = split_data(X, y, "classification")
    trained = train_model(split.X_train, split.y_train, "classification", "decision_tree")
    data = dumps_pipeline(trained.pipeline)
    restored = loads_pipeline(data)
    assert list(restored.predict(split.X_test)) == list(trained.pipeline.predict(split.X_test))
    assert len(sha256_hex(data)) == 64
    assert sha256_hex(data) == sha256_hex(bytes(data))
    assert sha256_hex(data) != sha256_hex(data + b"x")


def test_metadata_describes_the_model_without_any_data_rows() -> None:
    X, y = separate_target(training_frame(), "target")
    split = split_data(X, y, "classification")
    trained = train_model(split.X_train, split.y_train, "classification", "logistic_regression")
    schema = build_feature_schema(split.X_train)
    metadata = build_metadata(
        model_id="md_1",
        version=2,
        experiment_id="ex_1",
        run_id="rn_1",
        trained=trained,
        metric="f1",
        metrics={"f1": 0.9},
        feature_schema=schema,
        split_info={"n_train": 48},
        target_column="target",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert metadata["version"] == 2 and metadata["task"] == "classification"
    assert metadata["classes"] == ["no", "yes"]
    assert metadata["feature_schema"] == schema
    assert metadata["preprocessing"]["numeric_columns"] == ["age"]
    assert metadata["preprocessing"]["categorical_columns"] == ["city", "member"]
    assert "scikit-learn" in metadata["library_versions"]
    assert "target" not in [s["name"] for s in metadata["feature_schema"]]


# --- strict input validation --------------------------------------------------------------------

SCHEMA = [
    {"name": "age", "kind": "numeric", "value_type": "number", "categories": None},
    {"name": "city", "kind": "categorical", "value_type": "string", "categories": ["Oslo"]},
    {"name": "member", "kind": "categorical", "value_type": "boolean", "categories": None},
]
GOOD = {"age": 30, "city": "Oslo", "member": True}


def issues_for(*instances: dict) -> list[dict[str, str]]:
    with pytest.raises(InstanceValidationError) as excinfo:
        instances_to_frame(SCHEMA, list(instances))
    return excinfo.value.issues


def test_valid_instances_become_a_frame_in_schema_order() -> None:
    frame = instances_to_frame(SCHEMA, [{"member": False, "city": "Oslo", "age": 41.5}, GOOD])
    assert list(frame.columns) == ["age", "city", "member"]
    assert frame["age"].dtype == "float64"
    assert frame["age"].tolist() == [41.5, 30.0]


def test_null_is_accepted_and_becomes_missing() -> None:
    frame = instances_to_frame(SCHEMA, [{"age": None, "city": None, "member": None}])
    assert frame.isna().all(axis=None)


def test_unseen_categories_are_accepted() -> None:
    frame = instances_to_frame(SCHEMA, [{**GOOD, "city": "Atlantis"}])
    assert frame["city"].tolist() == ["Atlantis"]


def test_unknown_and_missing_fields_are_rejected() -> None:
    assert issues_for({**GOOD, "extra": 1}) == [
        {"field": "instances[0].extra", "issue": "unknown field"}
    ]
    assert issues_for({"age": 1, "city": "Oslo"}) == [
        {"field": "instances[0].member", "issue": "required field is missing"}
    ]


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("age", "30", "must be a finite number"),
        ("age", True, "must be a finite number"),
        ("age", float("inf"), "must be a finite number"),
        ("age", float("nan"), "must be a finite number"),
        ("age", [1], "must be a finite number"),
        ("city", 5, "must be a string"),
        ("city", "x" * (MAX_STRING_LENGTH + 1), f"must be at most {MAX_STRING_LENGTH} characters"),
        ("member", "yes", "must be true or false"),
        ("member", 1, "must be true or false"),
    ],
)
def test_wrong_types_are_rejected(field: str, value: object, issue: str) -> None:
    assert issues_for({**GOOD, field: value}) == [
        {"field": f"instances[0].{field}", "issue": issue}
    ]


def test_issues_locate_the_row_and_never_echo_values() -> None:
    issues = issues_for(GOOD, {**GOOD, "age": "SECRET_VALUE"})
    assert issues == [{"field": "instances[1].age", "issue": "must be a finite number"}]
    assert "SECRET_VALUE" not in str(issues)


def test_the_number_of_reported_issues_is_capped() -> None:
    issues = issues_for(*[{"nope": 1}] * 50)
    assert len(issues) == MAX_REPORTED_ISSUES


def test_long_unknown_field_names_are_truncated() -> None:
    (issue, *_) = issues_for({**GOOD, "k" * 500: 1})
    assert len(issue["field"]) < 100


def test_results_are_converted_to_plain_json_values() -> None:
    assert jsonable_values(np.array([1.5, np.nan, np.inf])) == [1.5, None, None]
    assert jsonable_values(np.array(["a", "b"])) == ["a", "b"]
    assert jsonable_values(np.array([1, 2])) == [1, 2]
