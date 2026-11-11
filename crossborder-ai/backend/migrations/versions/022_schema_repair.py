"""repair production schema drift

Revision ID: 022_schema_repair
Revises: 021_marketing_video_projects
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "022_schema_repair"
down_revision: Union[str, None] = "021_marketing_video_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_columns(table_name)}


def _index_map(inspector: sa.Inspector, table_name: str) -> dict[str, dict]:
    return {item["name"]: item for item in inspector.get_indexes(table_name)}


def _unique_column_sets(inspector: sa.Inspector, table_name: str) -> set[frozenset[str]]:
    return {
        frozenset(item.get("column_names") or [])
        for item in inspector.get_unique_constraints(table_name)
    }


def _add_column_if_missing(
    inspector: sa.Inspector,
    table_name: str,
    column: sa.Column,
) -> None:
    if column.name not in _column_names(inspector, table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    """补齐曾被 stamp head 跳过的历史迁移 DDL。

    生产库已经标记到 021，但 011、013、019 的部分 DDL 未落库。
    本迁移按实际 schema 判断，正常库上保持幂等。
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    uuid_type = (
        sa.String(36)
        if bind.dialect.name == "sqlite"
        else postgresql.UUID(as_uuid=True)
    )

    _add_column_if_missing(
        inspector,
        "batch_jobs",
        sa.Column("product_id", uuid_type, nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "batch_jobs",
        sa.Column("listing_id", uuid_type, nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "image_generation_tasks",
        sa.Column("num_outputs", sa.Integer(), nullable=False, server_default="1"),
    )
    _add_column_if_missing(
        inspector,
        "image_generation_tasks",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_column_if_missing(
        inspector,
        "image_generation_tasks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "image_generation_tasks",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "product_variants",
        sa.Column(
            "daily_sales_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    inspector = sa.inspect(bind)
    if bind.dialect.name != "sqlite":
        foreign_keys = {
            item.get("name")
            for item in inspector.get_foreign_keys("batch_jobs")
        }
        if "fk_batch_jobs_product_id" not in foreign_keys:
            op.create_foreign_key(
                "fk_batch_jobs_product_id",
                "batch_jobs",
                "products",
                ["product_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "fk_batch_jobs_listing_id" not in foreign_keys:
            op.create_foreign_key(
                "fk_batch_jobs_listing_id",
                "batch_jobs",
                "listing_drafts",
                ["listing_id"],
                ["id"],
                ondelete="SET NULL",
            )

    batch_indexes = _index_map(inspector, "batch_jobs")
    if "ix_batch_jobs_product_id" not in batch_indexes:
        op.create_index(
            "ix_batch_jobs_product_id",
            "batch_jobs",
            ["product_id"],
        )
    if "ix_batch_jobs_listing_id" not in batch_indexes:
        op.create_index(
            "ix_batch_jobs_listing_id",
            "batch_jobs",
            ["listing_id"],
        )

    # 012 目标是把 URL 唯一性收敛到 user_id + url，并保留普通 URL 索引。
    product_indexes = _index_map(inspector, "products")
    url_index = product_indexes.get("ix_products_url")
    if url_index and url_index.get("unique"):
        op.drop_index("ix_products_url", table_name="products")
        product_indexes.pop("ix_products_url", None)

    if "ix_products_url" not in product_indexes:
        op.create_index("ix_products_url", "products", ["url"], unique=False)

    tenant_columns = frozenset({"user_id", "url"})
    if tenant_columns not in _unique_column_sets(inspector, "products"):
        if bind.dialect.name == "sqlite":
            op.create_index(
                "uq_products_user_url",
                "products",
                ["user_id", "url"],
                unique=True,
            )
        else:
            op.create_unique_constraint(
                "uq_products_user_url",
                "products",
                ["user_id", "url"],
            )


def downgrade() -> None:
    """修复迁移不回删历史迁移拥有的列。"""

    # 011、013、019 才是这些列的所有者，降级本修复迁移时保留数据。
