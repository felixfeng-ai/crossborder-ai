"""create canonical listing drafts and compliance reports

Revision ID: 010_create_listing_drafts
Revises: 009_create_image_generation_tasks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "010_create_listing_drafts"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listing_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="en"),
        sa.Column("tone", sa.String(50), nullable=False, server_default="professional"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("bullet_points", sa.Text(), nullable=True),
        sa.Column("seo_title", sa.String(500), nullable=True),
        sa.Column("seo_description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("compliance_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("compliance_violations", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ai_model_used", sa.String(100), nullable=True),
        sa.Column("image_task_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_listing_drafts_user_id", "listing_drafts", ["user_id"])
    op.create_index("ix_listing_drafts_product_id", "listing_drafts", ["product_id"])
    op.create_index("ix_listing_drafts_content_hash", "listing_drafts", ["content_hash"])

    op.create_table(
        "listing_compliance_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listing_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("listing_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("violations", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(30), nullable=False, server_default="generation"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_listing_compliance_reports_listing_id",
        "listing_compliance_reports",
        ["listing_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_listing_compliance_reports_listing_id",
        table_name="listing_compliance_reports",
    )
    op.drop_table("listing_compliance_reports")
    op.drop_index("ix_listing_drafts_content_hash", table_name="listing_drafts")
    op.drop_index("ix_listing_drafts_product_id", table_name="listing_drafts")
    op.drop_index("ix_listing_drafts_user_id", table_name="listing_drafts")
    op.drop_table("listing_drafts")
