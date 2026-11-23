"""add user avatar storage metadata

Revision ID: 082_user_avatar
Revises: 081_work_item_channel_scope
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "082_user_avatar"
down_revision: Union[str, None] = "081_work_item_channel_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_storage_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "avatar_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_storage_key")
