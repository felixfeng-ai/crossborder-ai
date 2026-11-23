"""create raw integration events and channel leases

Revision ID: 060_integration_events
Revises: 059_shopify_channel_workspace
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "060_integration_events"
down_revision: Union[str, None] = "059_shopify_channel_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_event_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("external_resource_id", sa.String(length=200), nullable=True),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("fingerprint", sa.String(length=160), nullable=False),
        sa.Column(
            "signature_verified",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="received",
        ),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "external_event_id",
            name="uq_integration_events_external",
        ),
    )
    for column in (
        "workspace_id",
        "external_event_id",
        "external_resource_id",
        "fingerprint",
        "status",
    ):
        op.create_index(
            f"ix_integration_events_{column}",
            "integration_events",
            [column],
        )

    op.create_table(
        "integration_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(length=200), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("owner_token", sa.String(length=120), nullable=False),
        sa.Column(
            "locked_until",
            sa.DateTime(timezone=True),
            nullable=False,
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
            name="uq_integration_leases_resource",
        ),
    )
    for column in ("workspace_id", "locked_until"):
        op.create_index(
            f"ix_integration_leases_{column}",
            "integration_leases",
            [column],
        )


def downgrade() -> None:
    for column in ("locked_until", "workspace_id"):
        op.drop_index(
            f"ix_integration_leases_{column}",
            table_name="integration_leases",
        )
    op.drop_table("integration_leases")
    for column in (
        "status",
        "fingerprint",
        "external_resource_id",
        "external_event_id",
        "workspace_id",
    ):
        op.drop_index(
            f"ix_integration_events_{column}",
            table_name="integration_events",
        )
    op.drop_table("integration_events")
