"""add workspace agent autonomy policies and dual approvals

Revision ID: 067_agent_autonomy
Revises: 066_workspace_subscription
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "067_agent_autonomy"
down_revision: Union[str, None] = "066_workspace_subscription"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_autonomy_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_id", sa.String(length=80), nullable=False),
        sa.Column(
            "autonomy_level",
            sa.String(length=20),
            nullable=False,
            server_default="confirm",
        ),
        sa.Column(
            "conditions_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
            "workspace_id",
            "action_id",
            name="uq_agent_autonomy_policies_action",
        ),
    )
    for column in ("workspace_id", "action_id", "created_by_user_id"):
        op.create_index(
            f"ix_agent_autonomy_policies_{column}",
            "agent_autonomy_policies",
            [column],
        )
    op.create_index(
        "ix_agent_autonomy_policies_workspace_enabled",
        "agent_autonomy_policies",
        ["workspace_id", "enabled"],
    )

    with op.batch_alter_table("action_runs") as batch:
        batch.add_column(
            sa.Column(
                "policy_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("policy_version", sa.Integer(), nullable=True)
        )
        batch.add_column(
            sa.Column("policy_snapshot_json", sa.Text(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_action_runs_policy_id",
            "agent_autonomy_policies",
            ["policy_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_action_runs_policy_id",
        "action_runs",
        ["policy_id"],
    )

    op.create_table(
        "action_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "action_run_id",
            "user_id",
            name="uq_action_approvals_run_user",
        ),
    )
    for column in ("workspace_id", "action_run_id", "user_id"):
        op.create_index(
            f"ix_action_approvals_{column}",
            "action_approvals",
            [column],
        )


def downgrade() -> None:
    for column in ("user_id", "action_run_id", "workspace_id"):
        op.drop_index(
            f"ix_action_approvals_{column}",
            table_name="action_approvals",
        )
    op.drop_table("action_approvals")

    op.drop_index("ix_action_runs_policy_id", table_name="action_runs")
    with op.batch_alter_table("action_runs") as batch:
        batch.drop_constraint(
            "fk_action_runs_policy_id",
            type_="foreignkey",
        )
        batch.drop_column("policy_snapshot_json")
        batch.drop_column("policy_version")
        batch.drop_column("policy_id")

    op.drop_index(
        "ix_agent_autonomy_policies_workspace_enabled",
        table_name="agent_autonomy_policies",
    )
    for column in ("created_by_user_id", "action_id", "workspace_id"):
        op.drop_index(
            f"ix_agent_autonomy_policies_{column}",
            table_name="agent_autonomy_policies",
        )
    op.drop_table("agent_autonomy_policies")
