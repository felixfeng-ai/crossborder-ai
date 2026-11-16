"""add product image gallery and source video

Revision ID: 049_product_media
Revises: 048_marketing_image_suites
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "049_product_media"
down_revision: Union[str, None] = "048_marketing_image_suites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "image_urls",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "products",
        sa.Column("video_url", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "video_url")
    op.drop_column("products", "image_urls")
