"""add multi-platform A/B marketing copy assets

Revision ID: 040_marketing_copy_assets
Revises: 039_generated_image_assets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "040_marketing_copy_assets"
down_revision: Union[str, None] = "039_generated_image_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketing_copy_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
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
        sa.Column("variant_key", sa.String(length=5), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cta", sa.String(length=500), nullable=False),
        sa.Column("hashtags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("keywords_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ready"),
        sa.Column(
            "compliance_status",
            sa.String(length=20),
            nullable=False,
            server_default="pass",
        ),
        sa.Column("violations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="agent"),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "batch_id",
            "platform",
            "variant_key",
            name="uq_marketing_copy_batch_platform_variant",
        ),
    )
    op.create_index(
        "ix_marketing_copy_assets_batch_id",
        "marketing_copy_assets",
        ["batch_id"],
    )
    op.create_index(
        "ix_marketing_copy_assets_user_id",
        "marketing_copy_assets",
        ["user_id"],
    )
    op.create_index(
        "ix_marketing_copy_assets_campaign_id",
        "marketing_copy_assets",
        ["campaign_id"],
    )
    op.create_index(
        "ix_marketing_copy_assets_platform",
        "marketing_copy_assets",
        ["platform"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_copy_assets_platform",
        table_name="marketing_copy_assets",
    )
    op.drop_index(
        "ix_marketing_copy_assets_campaign_id",
        table_name="marketing_copy_assets",
    )
    op.drop_index(
        "ix_marketing_copy_assets_user_id",
        table_name="marketing_copy_assets",
    )
    op.drop_index(
        "ix_marketing_copy_assets_batch_id",
        table_name="marketing_copy_assets",
    )
    op.drop_table("marketing_copy_assets")
