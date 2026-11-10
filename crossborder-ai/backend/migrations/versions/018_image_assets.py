"""create image workbench assets

Revision ID: 018_image_assets
Revises: 017_agent_history
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "018_image_assets"
down_revision: Union[str, None] = "017_agent_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="upload"),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("preset_id", sa.String(50), nullable=True),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("background_mode", sa.String(20), nullable=True),
        sa.Column(
            "source_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("image_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_image_assets_user_id", "image_assets", ["user_id"])
    op.create_index(
        "ix_image_assets_source_asset_id",
        "image_assets",
        ["source_asset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_assets_source_asset_id", table_name="image_assets")
    op.drop_index("ix_image_assets_user_id", table_name="image_assets")
    op.drop_table("image_assets")
