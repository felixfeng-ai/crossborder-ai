"""add data retention audit table

Revision ID: 023_data_retention_runs
Revises: 022_schema_repair
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "023_data_retention_runs"
down_revision: Union[str, None] = "022_schema_repair"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    bind = op.get_bind()
    return sa.String(36) if bind.dialect.name == "sqlite" else postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "data_retention_runs",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("store_check_retention_days", sa.Integer(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_counts", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_data_retention_runs_status",
        "data_retention_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_data_retention_runs_status", table_name="data_retention_runs")
    op.drop_table("data_retention_runs")
