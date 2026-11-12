"""add campaign publications and performance snapshots

Revision ID: 041_marketing_distribution
Revises: 040_marketing_copy_assets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "041_marketing_distribution"
down_revision: Union[str, None] = "040_marketing_copy_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketing_campaign_publications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketing_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "copy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketing_copy_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listing_drafts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "publication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("external_product_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id",
            "campaign_id",
            "platform",
            "idempotency_key",
            name="uq_marketing_publication_idempotency",
        ),
    )
    for column in ("user_id", "campaign_id", "copy_id", "publication_id", "platform"):
        op.create_index(
            f"ix_marketing_campaign_publications_{column}",
            "marketing_campaign_publications",
            [column],
        )

    op.create_table(
        "marketing_performance_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketing_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spend", sa.Float(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "campaign_id",
            "platform",
            "source",
            "period_start",
            "period_end",
            name="uq_marketing_performance_period",
        ),
    )
    for column in ("user_id", "campaign_id", "platform"):
        op.create_index(
            f"ix_marketing_performance_snapshots_{column}",
            "marketing_performance_snapshots",
            [column],
        )


def downgrade() -> None:
    for column in ("platform", "campaign_id", "user_id"):
        op.drop_index(
            f"ix_marketing_performance_snapshots_{column}",
            table_name="marketing_performance_snapshots",
        )
    op.drop_table("marketing_performance_snapshots")
    for column in ("platform", "publication_id", "copy_id", "campaign_id", "user_id"):
        op.drop_index(
            f"ix_marketing_campaign_publications_{column}",
            table_name="marketing_campaign_publications",
        )
    op.drop_table("marketing_campaign_publications")
