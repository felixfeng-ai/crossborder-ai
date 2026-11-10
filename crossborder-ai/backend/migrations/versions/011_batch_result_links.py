"""link batch jobs to created products and listings

Revision ID: 011_batch_result_links
Revises: 010_create_listing_drafts
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "011_batch_result_links"
down_revision: Union[str, None] = "010_create_listing_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("batch_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_batch_jobs_product_id",
            "products",
            ["product_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_batch_jobs_listing_id",
            "listing_drafts",
            ["listing_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_batch_jobs_product_id", "batch_jobs", ["product_id"])
    op.create_index("ix_batch_jobs_listing_id", "batch_jobs", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_batch_jobs_listing_id", table_name="batch_jobs")
    op.drop_index("ix_batch_jobs_product_id", table_name="batch_jobs")
    with op.batch_alter_table("batch_jobs") as batch_op:
        batch_op.drop_constraint(
            "fk_batch_jobs_listing_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_batch_jobs_product_id",
            type_="foreignkey",
        )
        batch_op.drop_column("listing_id")
        batch_op.drop_column("product_id")
