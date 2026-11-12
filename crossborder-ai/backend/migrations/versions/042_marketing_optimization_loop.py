"""add copy-level metrics and ab performance status

Revision ID: 042_marketing_optimization
Revises: 041_marketing_distribution
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "042_marketing_optimization"
down_revision: Union[str, None] = "041_marketing_distribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("marketing_copy_assets") as batch_op:
        batch_op.add_column(
            sa.Column(
                "performance_status",
                sa.String(length=30),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.add_column(
            sa.Column(
                "performance_metrics_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_evaluated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    with op.batch_alter_table("marketing_performance_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column(
                "copy_id",
                UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "scope_key",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )
        batch_op.create_foreign_key(
            "fk_marketing_performance_snapshots_copy_id",
            "marketing_copy_assets",
            ["copy_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint(
            "uq_marketing_performance_period",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_marketing_performance_period",
            [
                "campaign_id",
                "platform",
                "source",
                "period_start",
                "period_end",
                "scope_key",
            ],
        )
    op.create_index(
        "ix_marketing_performance_snapshots_copy_id",
        "marketing_performance_snapshots",
        ["copy_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_performance_snapshots_copy_id",
        table_name="marketing_performance_snapshots",
    )
    with op.batch_alter_table("marketing_performance_snapshots") as batch_op:
        batch_op.drop_constraint(
            "uq_marketing_performance_period",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_marketing_performance_period",
            [
                "campaign_id",
                "platform",
                "source",
                "period_start",
                "period_end",
            ],
        )
        batch_op.drop_constraint(
            "fk_marketing_performance_snapshots_copy_id",
            type_="foreignkey",
        )
        batch_op.drop_column("scope_key")
        batch_op.drop_column("copy_id")

    with op.batch_alter_table("marketing_copy_assets") as batch_op:
        batch_op.drop_column("last_evaluated_at")
        batch_op.drop_column("performance_metrics_json")
        batch_op.drop_column("performance_status")
