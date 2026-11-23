"""add category to image assets

Revision ID: 080_image_asset_category
Revises: 079_user_sessions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "080_image_asset_category"
down_revision: Union[str, None] = "079_user_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """素材库分类：只新增列，旧数据统一落到 other（未归类）。"""

    op.add_column(
        "image_assets",
        sa.Column(
            "category",
            sa.String(length=20),
            nullable=False,
            server_default="other",
        ),
    )
    op.create_index(
        "ix_image_assets_category",
        "image_assets",
        ["category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_assets_category", table_name="image_assets")
    op.drop_column("image_assets", "category")
