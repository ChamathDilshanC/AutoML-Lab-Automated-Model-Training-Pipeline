"""Add Supabase identity fields to users.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("auth_subject", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_users_auth_subject", ["auth_subject"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_auth_subject", type_="unique")
        batch_op.drop_column("auth_subject")
        batch_op.drop_column("email")
