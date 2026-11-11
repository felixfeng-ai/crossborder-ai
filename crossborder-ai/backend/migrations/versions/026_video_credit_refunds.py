"""add video credit refund tracking

Revision ID: 026_video_credit_refunds
Revises: 025_credit_transactions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "026_video_credit_refunds"
down_revision: Union[str, None] = "025_credit_transactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_columns_if_missing(
    table_name: str,
    columns: list[sa.Column],
) -> None:
    existing = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def upgrade() -> None:
    _add_columns_if_missing(
        "video_generation_tasks",
        [
            sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("credits_refunded", sa.Integer(), nullable=False, server_default="0"),
        ],
    )
    _add_columns_if_missing(
        "marketing_video_projects",
        [
            sa.Column("credits_refunded", sa.Integer(), nullable=False, server_default="0"),
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("marketing_video_projects") as batch:
        batch.drop_column("credits_refunded")
    with op.batch_alter_table("video_generation_tasks") as batch:
        batch.drop_column("credits_refunded")
        batch.drop_column("credits_charged")
