"""add image asset ordering and soft deletion

Revision ID: 068_media_library
Revises: 067_agent_autonomy
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "068_media_library"
down_revision: Union[str, None] = "067_agent_autonomy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("image_assets") as batch:
        batch.add_column(
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
    op.create_index(
        "ix_image_assets_sort_order",
        "image_assets",
        ["sort_order"],
    )
    op.create_index(
        "ix_image_assets_deleted_at",
        "image_assets",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_assets_deleted_at", table_name="image_assets")
    op.drop_index("ix_image_assets_sort_order", table_name="image_assets")
    with op.batch_alter_table("image_assets") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("sort_order")
