"""add channel scope to work items

Revision ID: 081_work_item_channel_scope
Revises: 080_image_asset_category
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "081_work_item_channel_scope"
down_revision: Union[str, None] = "080_image_asset_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增可空店铺归属；历史任务不猜测归属。"""

    op.add_column(
        "work_items",
        sa.Column("channel_type", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "work_items",
        sa.Column("channel_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_work_items_channel_type",
        "work_items",
        ["channel_type"],
        unique=False,
    )
    op.create_index(
        "ix_work_items_channel_id",
        "work_items",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        "ix_work_items_channel_scope",
        "work_items",
        ["workspace_id", "channel_type", "channel_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_work_items_channel_scope", table_name="work_items")
    op.drop_index("ix_work_items_channel_id", table_name="work_items")
    op.drop_index("ix_work_items_channel_type", table_name="work_items")
    op.drop_column("work_items", "channel_id")
    op.drop_column("work_items", "channel_type")
