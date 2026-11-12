"""add own supply product fields

Revision ID: 034_own_supply_products
Revises: 033_video_quality_engine
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "034_own_supply_products"
down_revision: Union[str, None] = "033_video_quality_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "origin_type",
            sa.String(length=20),
            nullable=False,
            server_default="1688",
        ),
    )
    op.create_index(
        "ix_products_origin_type",
        "products",
        ["origin_type"],
    )
    op.add_column(
        "products",
        sa.Column("brand_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column(
            "cost_currency",
            sa.String(length=8),
            nullable=False,
            server_default="CNY",
        ),
    )
    op.add_column(
        "products",
        sa.Column("moq", sa.Integer(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
    )

    op.add_column(
        "batch_jobs",
        sa.Column(
            "origin_type",
            sa.String(length=20),
            nullable=False,
            server_default="own",
        ),
    )
    op.add_column(
        "batch_jobs",
        sa.Column("main_image_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "batch_jobs",
        sa.Column("brand_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "batch_jobs",
        sa.Column(
            "cost_currency",
            sa.String(length=8),
            nullable=False,
            server_default="CNY",
        ),
    )
    op.add_column(
        "batch_jobs",
        sa.Column("moq", sa.Integer(), nullable=True),
    )
    op.add_column(
        "batch_jobs",
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "batch_jobs",
        sa.Column("stock_quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "batch_jobs",
        sa.Column("sku", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    for column in (
        "sku",
        "stock_quantity",
        "lead_time_days",
        "moq",
        "cost_currency",
        "brand_name",
        "main_image_url",
        "origin_type",
    ):
        op.drop_column("batch_jobs", column)

    op.drop_column("products", "lead_time_days")
    op.drop_column("products", "moq")
    op.drop_column("products", "cost_currency")
    op.drop_column("products", "brand_name")
    op.drop_index("ix_products_origin_type", table_name="products")
    op.drop_column("products", "origin_type")
