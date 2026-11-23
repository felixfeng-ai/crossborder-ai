"""add controlled action runtime records

Revision ID: 052_action_runtime
Revises: 051_agent_work_items
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "052_action_runtime"
down_revision: Union[str, None] = "051_agent_work_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建立动作计划、执行、回读与失败恢复所需的持久记录。"""

    op.create_table(
        "action_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action_id", sa.String(length=80), nullable=False),
        sa.Column(
            "action_version",
            sa.String(length=20),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=False),
        sa.Column(
            "input_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("before_snapshot_json", sa.Text(), nullable=True),
        sa.Column("after_snapshot_json", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="planned",
        ),
        sa.Column(
            "risk_level",
            sa.String(length=20),
            nullable=False,
            server_default="low",
        ),
        sa.Column(
            "autonomy_level",
            sa.String(length=20),
            nullable=False,
            server_default="confirm",
        ),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column(
            "attempt",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("verification_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "confirmed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "action_id",
            "idempotency_key",
            name="uq_action_runs_workspace_action_idempotency",
        ),
    )
    for column in (
        "workspace_id",
        "work_item_id",
        "agent_turn_id",
        "action_id",
        "platform",
        "status",
        "confirmed_by_user_id",
    ):
        op.create_index(f"ix_action_runs_{column}", "action_runs", [column])
    op.create_index(
        "ix_action_runs_workspace_status",
        "action_runs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_action_runs_workspace_platform",
        "action_runs",
        ["workspace_id", "platform"],
    )


def downgrade() -> None:
    """动作记录包含审计价值，但回滚迁移时仍按依赖顺序移除。"""

    op.drop_index("ix_action_runs_workspace_platform", table_name="action_runs")
    op.drop_index("ix_action_runs_workspace_status", table_name="action_runs")
    for column in (
        "confirmed_by_user_id",
        "status",
        "platform",
        "action_id",
        "agent_turn_id",
        "work_item_id",
        "workspace_id",
    ):
        op.drop_index(f"ix_action_runs_{column}", table_name="action_runs")
    op.drop_table("action_runs")
