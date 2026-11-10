"""scope product URL uniqueness to each user

Revision ID: 012_tenant_product_url
Revises: 011_batch_result_links
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "012_tenant_product_url"
down_revision: Union[str, None] = "011_batch_result_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 003 中的 unique=True,index=True 会生成唯一索引 ix_products_url，
    # 它不等于 unique constraint，必须单独删除，否则跨用户仍不能复用 URL。
    for index in inspector.get_indexes("products"):
        if index.get("unique") and set(index.get("column_names") or []) == {"url"}:
            op.drop_index(index["name"], table_name="products")

    for constraint in inspector.get_unique_constraints("products"):
        if set(constraint.get("column_names") or []) == {"url"}:
            op.drop_constraint(constraint["name"], "products", type_="unique")
            break

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
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.drop_index("uq_products_user_url", table_name="products")
    else:
        op.drop_constraint("uq_products_user_url", "products", type_="unique")
    op.create_index("ix_products_url", "products", ["url"], unique=True)
