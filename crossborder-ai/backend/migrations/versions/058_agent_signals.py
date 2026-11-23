"""create agent signals and integration cursors

Revision ID: 058_agent_signals
Revises: 057_notifications
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "058_agent_signals"
down_revision: Union[str, None] = "057_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("signal_type", sa.String(length=60), nullable=False),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("fingerprint", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            "fingerprint",
            "version",
            name="uq_agent_signals_fingerprint_version",
        ),
    )
    for column in (
        "workspace_id",
        "signal_type",
        "fingerprint",
        "status",
        "work_item_id",
    ):
        op.create_index(
            f"ix_agent_signals_{column}",
            "agent_signals",
            [column],
        )
    op.create_index(
        "ix_agent_signals_workspace_status",
        "agent_signals",
        ["workspace_id", "status"],
    )

    op.create_table(
        "integration_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(length=200), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("cursor_value", sa.String(length=500), nullable=False),
        sa.Column(
            "overlap_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        sa.Column(
            "last_success_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
            "channel_id",
            "resource_type",
            name="uq_integration_cursors_resource",
        ),
    )
    op.create_index(
        "ix_integration_cursors_workspace_id",
        "integration_cursors",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_cursors_workspace_id",
        table_name="integration_cursors",
    )
    op.drop_table("integration_cursors")
    op.drop_index(
        "ix_agent_signals_workspace_status",
        table_name="agent_signals",
    )
    for column in (
        "work_item_id",
        "status",
        "fingerprint",
        "signal_type",
        "workspace_id",
    ):
        op.drop_index(
            f"ix_agent_signals_{column}",
            table_name="agent_signals",
        )
    op.drop_table("agent_signals")
