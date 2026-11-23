"""create agent days and daily plan items

Revision ID: 056_agent_days
Revises: 055_customer_reply_language
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "056_agent_days"
down_revision: Union[str, None] = "055_customer_reply_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="planning",
        ),
        sa.Column(
            "plan_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "watch_mode",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("morning_brief_json", sa.Text(), nullable=True),
        sa.Column("closeout_json", sa.Text(), nullable=True),
        sa.Column("morning_brief_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "business_date",
            name="uq_agent_days_workspace_date",
        ),
    )
    op.create_index("ix_agent_days_workspace_id", "agent_days", ["workspace_id"])
    op.create_index("ix_agent_days_status", "agent_days", ["status"])

    op.create_table(
        "daily_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_day_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_days.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column(
            "priority_score",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("expected_action", sa.Text(), nullable=True),
        sa.Column("policy_id", sa.String(length=80), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="planned",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "agent_day_id",
            "work_item_id",
            name="uq_daily_plan_items_day_work",
        ),
    )
    for column in (
        "workspace_id",
        "agent_day_id",
        "work_item_id",
        "category",
        "status",
    ):
        op.create_index(
            f"ix_daily_plan_items_{column}",
            "daily_plan_items",
            [column],
        )


def downgrade() -> None:
    for column in (
        "status",
        "category",
        "work_item_id",
        "agent_day_id",
        "workspace_id",
    ):
        op.drop_index(
            f"ix_daily_plan_items_{column}",
            table_name="daily_plan_items",
        )
    op.drop_table("daily_plan_items")
    op.drop_index("ix_agent_days_status", table_name="agent_days")
    op.drop_index("ix_agent_days_workspace_id", table_name="agent_days")
    op.drop_table("agent_days")
