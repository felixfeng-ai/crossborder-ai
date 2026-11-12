"""link generated images to reusable assets

Revision ID: 039_generated_image_assets
Revises: 038_campaign_assets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "039_generated_image_assets"
down_revision: Union[str, None] = "038_campaign_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("image_assets") as batch_op:
        batch_op.add_column(
            sa.Column("generation_task_id", UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("variant_index", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_image_assets_generation_task_id",
            "image_generation_tasks",
            ["generation_task_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_image_assets_generation_variant",
            ["generation_task_id", "variant_index"],
        )
    op.create_index(
        "ix_image_assets_generation_task_id",
        "image_assets",
        ["generation_task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_assets_generation_task_id",
        table_name="image_assets",
    )
    with op.batch_alter_table("image_assets") as batch_op:
        batch_op.drop_constraint(
            "uq_image_assets_generation_variant",
            type_="unique",
        )
        batch_op.drop_constraint(
            "fk_image_assets_generation_task_id",
            type_="foreignkey",
        )
        batch_op.drop_column("variant_index")
        batch_op.drop_column("generation_task_id")
