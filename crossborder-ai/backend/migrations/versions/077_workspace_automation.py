"""scope automation preferences and task states to workspaces

Revision ID: 077_workspace_automation
Revises: 076_media_workspace_idem
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "077_workspace_automation"
down_revision: Union[str, None] = "076_media_workspace_idem"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    return (
        postgresql.UUID(as_uuid=True)
        if op.get_bind().dialect.name == "postgresql"
        else sa.String(36)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("workspace_automation_preferences"):
        op.create_table(
            "workspace_automation_preferences",
            sa.Column(
                "workspace_id",
                _uuid_type(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "user_id",
                _uuid_type(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "daily_store_check",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "daily_operations_monitor",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "shopify_auto_sync",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "ab_auto_pause",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_workspace_automation_preferences_user_id",
            "workspace_automation_preferences",
            ["user_id"],
        )

    if not inspector.has_table("workspace_automation_task_states"):
        op.create_table(
            "workspace_automation_task_states",
            sa.Column(
                "workspace_id",
                _uuid_type(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("task", sa.String(50), primary_key=True),
            sa.Column(
                "user_id",
                _uuid_type(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("last_run_at", sa.DateTime(timezone=True)),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="never",
            ),
            sa.Column("error", sa.Text()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_workspace_automation_task_states_user_id",
            "workspace_automation_task_states",
            ["user_id"],
        )

    if inspector.has_table("automation_preferences"):
        op.execute(
            sa.text(
                """
                INSERT INTO workspace_automation_preferences (
                    workspace_id, user_id, daily_store_check,
                    daily_operations_monitor, shopify_auto_sync,
                    ab_auto_pause, updated_at
                )
                SELECT
                    workspaces.id,
                    automation_preferences.user_id,
                    automation_preferences.daily_store_check,
                    automation_preferences.daily_operations_monitor,
                    automation_preferences.shopify_auto_sync,
                    automation_preferences.ab_auto_pause,
                    automation_preferences.updated_at
                FROM automation_preferences
                JOIN workspaces
                  ON workspaces.owner_user_id = automation_preferences.user_id
                 AND workspaces.type = 'personal'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM workspace_automation_preferences existing
                    WHERE existing.workspace_id = workspaces.id
                )
                """
            )
        )

    if inspector.has_table("automation_task_states"):
        op.execute(
            sa.text(
                """
                INSERT INTO workspace_automation_task_states (
                    workspace_id, task, user_id, last_run_at,
                    status, error, updated_at
                )
                SELECT
                    workspaces.id,
                    automation_task_states.task,
                    automation_task_states.user_id,
                    automation_task_states.last_run_at,
                    automation_task_states.status,
                    automation_task_states.error,
                    automation_task_states.updated_at
                FROM automation_task_states
                JOIN workspaces
                  ON workspaces.owner_user_id = automation_task_states.user_id
                 AND workspaces.type = 'personal'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM workspace_automation_task_states existing
                    WHERE existing.workspace_id = workspaces.id
                      AND existing.task = automation_task_states.task
                )
                """
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_automation_task_states_user_id",
        table_name="workspace_automation_task_states",
    )
    op.drop_table("workspace_automation_task_states")
    op.drop_index(
        "ix_workspace_automation_preferences_user_id",
        table_name="workspace_automation_preferences",
    )
    op.drop_table("workspace_automation_preferences")
