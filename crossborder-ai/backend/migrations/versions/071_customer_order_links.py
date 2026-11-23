"""add customer order fact links

Revision ID: 071_customer_order_links
Revises: 070_customer_attachments
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "071_customer_order_links"
down_revision: Union[str, None] = "070_customer_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_order_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shopify_channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shopify_channels.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "external_order_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column("order_name", sa.String(length=120), nullable=True),
        sa.Column(
            "financial_status",
            sa.String(length=40),
            nullable=True,
        ),
        sa.Column(
            "fulfillment_status",
            sa.String(length=40),
            nullable=True,
        ),
        sa.Column(
            "tracking_company",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column(
            "tracking_number",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column("tracking_url", sa.Text(), nullable=True),
        sa.Column(
            "order_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "snapshot_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "fetched_at",
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
            "thread_id",
            name="uq_customer_order_links_thread",
        ),
    )
    for column in (
        "workspace_id",
        "thread_id",
        "shopify_channel_id",
        "external_order_id",
    ):
        op.create_index(
            f"ix_customer_order_links_{column}",
            "customer_order_links",
            [column],
        )


def downgrade() -> None:
    for column in (
        "external_order_id",
        "shopify_channel_id",
        "thread_id",
        "workspace_id",
    ):
        op.drop_index(
            f"ix_customer_order_links_{column}",
            table_name="customer_order_links",
        )
    op.drop_table("customer_order_links")
