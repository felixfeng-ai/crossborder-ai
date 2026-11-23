"""scope operations monitor settings to workspaces

Revision ID: 078_workspace_monitor_settings
Revises: 077_workspace_automation
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "078_workspace_monitor_settings"
down_revision: Union[str, None] = "077_workspace_automation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    return (
        postgresql.UUID(as_uuid=True)
        if op.get_bind().dialect.name == "postgresql"
        else sa.String(36)
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("workspace_monitor_settings"):
        op.create_table(
            "workspace_monitor_settings",
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
                "target_margin_rate",
                sa.Float(),
                nullable=False,
                server_default="25",
            ),
            sa.Column(
                "low_stock_days",
                sa.Integer(),
                nullable=False,
                server_default="7",
            ),
            sa.Column(
                "lead_time_days",
                sa.Integer(),
                nullable=False,
                server_default="14",
            ),
            sa.Column(
                "safety_stock_days",
                sa.Integer(),
                nullable=False,
                server_default="3",
            ),
            sa.Column(
                "platform_fee_rate",
                sa.Float(),
                nullable=False,
                server_default="0.15",
            ),
            sa.Column(
                "shipping_cost",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "cost_increase_alert_rate",
                sa.Float(),
                nullable=False,
                server_default="8",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_workspace_monitor_settings_user_id",
            "workspace_monitor_settings",
            ["user_id"],
        )

    if inspector.has_table("monitor_settings"):
        op.execute(
            sa.text(
                """
                INSERT INTO workspace_monitor_settings (
                    workspace_id, user_id, target_margin_rate,
                    low_stock_days, lead_time_days, safety_stock_days,
                    platform_fee_rate, shipping_cost,
                    cost_increase_alert_rate, updated_at
                )
                SELECT
                    workspaces.id,
                    monitor_settings.user_id,
                    monitor_settings.target_margin_rate,
                    monitor_settings.low_stock_days,
                    monitor_settings.lead_time_days,
                    monitor_settings.safety_stock_days,
                    monitor_settings.platform_fee_rate,
                    monitor_settings.shipping_cost,
                    monitor_settings.cost_increase_alert_rate,
                    monitor_settings.updated_at
                FROM monitor_settings
                JOIN workspaces
                  ON workspaces.owner_user_id = monitor_settings.user_id
                 AND workspaces.type = 'personal'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM workspace_monitor_settings existing
                    WHERE existing.workspace_id = workspaces.id
                )
                """
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_monitor_settings_user_id",
        table_name="workspace_monitor_settings",
    )
    op.drop_table("workspace_monitor_settings")
