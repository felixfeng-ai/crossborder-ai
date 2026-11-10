"""create unified platform publication records

Revision ID: 014_publications
Revises: 013_image_task_queue
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "014_publications"
down_revision: Union[str, None] = "013_image_task_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listing_drafts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("channel_id", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="publishing"),
        sa.Column("external_product_id", sa.String(255), nullable=True),
        sa.Column("external_url", sa.String(1000), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id",
            "platform",
            "idempotency_key",
            name="uq_publications_user_platform_idem",
        ),
    )
    op.create_index("ix_publications_user_id", "publications", ["user_id"])
    op.create_index("ix_publications_listing_id", "publications", ["listing_id"])
    op.create_index("ix_publications_platform", "publications", ["platform"])


def downgrade() -> None:
    op.drop_index("ix_publications_platform", table_name="publications")
    op.drop_index("ix_publications_listing_id", table_name="publications")
    op.drop_index("ix_publications_user_id", table_name="publications")
    op.drop_table("publications")
