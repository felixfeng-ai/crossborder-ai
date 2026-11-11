"""add Shopify compliance webhook audit

Revision ID: 024_shopify_compliance_events
Revises: 023_data_retention_runs
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "024_shopify_compliance_events"
down_revision: Union[str, None] = "023_data_retention_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    bind = op.get_bind()
    return sa.String(36) if bind.dialect.name == "sqlite" else postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "shopify_compliance_events",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("webhook_id", sa.String(length=128), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("shop_domain", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("action_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_shopify_compliance_events_webhook_id",
        "shopify_compliance_events",
        ["webhook_id"],
        unique=True,
    )
    op.create_index(
        "ix_shopify_compliance_events_topic",
        "shopify_compliance_events",
        ["topic"],
    )
    op.create_index(
        "ix_shopify_compliance_events_shop_domain",
        "shopify_compliance_events",
        ["shop_domain"],
    )
    op.create_index(
        "ix_shopify_compliance_events_status",
        "shopify_compliance_events",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_shopify_compliance_events_status", table_name="shopify_compliance_events")
    op.drop_index("ix_shopify_compliance_events_shop_domain", table_name="shopify_compliance_events")
    op.drop_index("ix_shopify_compliance_events_topic", table_name="shopify_compliance_events")
    op.drop_index("ix_shopify_compliance_events_webhook_id", table_name="shopify_compliance_events")
    op.drop_table("shopify_compliance_events")
