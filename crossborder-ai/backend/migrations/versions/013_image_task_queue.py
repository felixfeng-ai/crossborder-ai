"""add durable image task queue fields

Revision ID: 013_image_task_queue
Revises: 012_tenant_product_url
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "013_image_task_queue"
down_revision: Union[str, None] = "012_tenant_product_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("image_generation_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("num_outputs", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("image_generation_tasks") as batch_op:
        batch_op.drop_column("finished_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("attempts")
        batch_op.drop_column("num_outputs")
