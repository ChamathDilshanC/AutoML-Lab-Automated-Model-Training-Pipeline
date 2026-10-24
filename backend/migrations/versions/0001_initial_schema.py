"""Initial schema: datasets, experiments, runs, models, users and the audit log.

This is the baseline for PostgreSQL deployments (M8). A test checks that it produces exactly the
tables, columns, indexes and constraints that app/db/models.py declares, so change the models and
add a new revision together.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_events_created_at"), ["created_at"], unique=False
        )

    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("schema_summary", sa.JSON(), nullable=True),
        sa.Column("quality_warnings", sa.JSON(), nullable=True),
        sa.Column("validation_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
    )
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_datasets_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_username"), ["username"], unique=True)

    op.create_table(
        "experiments",
        sa.Column("experiment_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("algorithms", sa.JSON(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("test_size", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("selected_run_id", sa.String(length=64), nullable=True),
        sa.Column("split_info", sa.JSON(), nullable=True),
        sa.Column("library_versions", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
        ),
        sa.PrimaryKeyConstraint("experiment_id"),
        sa.UniqueConstraint("owner_id", "idempotency_key"),
    )
    with op.batch_alter_table("experiments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_experiments_dataset_id"), ["dataset_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_experiments_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(
            "ix_experiments_status_created", ["status", "created_at"], unique=False
        )

    op.create_table(
        "experiment_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("experiment_id", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=False),
        sa.Column("cv_score", sa.Float(), nullable=True),
        sa.Column("cv_folds", sa.Integer(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.experiment_id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("experiment_id", "algorithm"),
    )
    with op.batch_alter_table("experiment_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_experiment_runs_experiment_id"), ["experiment_id"], unique=False
        )

    op.create_table(
        "models",
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("experiment_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=False),
        sa.Column("feature_schema", sa.JSON(), nullable=False),
        sa.Column("classes", sa.JSON(), nullable=True),
        sa.Column("library_versions", sa.JSON(), nullable=False),
        sa.Column("artifact_key", sa.String(length=512), nullable=False),
        sa.Column("metadata_key", sa.String(length=512), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_bytes", sa.Integer(), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.experiment_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["experiment_runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("model_id"),
        sa.UniqueConstraint("owner_id", "dataset_id", "target_column", "task", "version"),
    )
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_models_dataset_id"), ["dataset_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_models_experiment_id"), ["experiment_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_models_owner_id"), ["owner_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_models_owner_id"))
        batch_op.drop_index(batch_op.f("ix_models_experiment_id"))
        batch_op.drop_index(batch_op.f("ix_models_dataset_id"))

    op.drop_table("models")
    with op.batch_alter_table("experiment_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_experiment_runs_experiment_id"))

    op.drop_table("experiment_runs")
    with op.batch_alter_table("experiments", schema=None) as batch_op:
        batch_op.drop_index("ix_experiments_status_created")
        batch_op.drop_index(batch_op.f("ix_experiments_owner_id"))
        batch_op.drop_index(batch_op.f("ix_experiments_dataset_id"))

    op.drop_table("experiments")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_username"))

    op.drop_table("users")
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_datasets_owner_id"))

    op.drop_table("datasets")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_events_created_at"))

    op.drop_table("audit_events")
