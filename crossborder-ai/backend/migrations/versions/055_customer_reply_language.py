"""add customer message and reply draft language fields

Revision ID: 055_customer_reply_language
Revises: 054_customer_channels
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "055_customer_reply_language"
down_revision: Union[str, None] = "054_customer_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customer_messages") as batch:
        batch.add_column(
            sa.Column("language", sa.String(length=20), nullable=True)
        )
    with op.batch_alter_table("reply_drafts") as batch:
        batch.add_column(
            sa.Column("source_language", sa.String(length=20), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("reply_drafts") as batch:
        batch.drop_column("source_language")
    with op.batch_alter_table("customer_messages") as batch:
        batch.drop_column("language")
