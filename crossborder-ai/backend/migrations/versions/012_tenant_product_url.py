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
    if bind.dialect.name == "sqlite":
        # New SQLite databases get the composite constraint from SQLAlchemy
        # metadata. Legacy SQLite files are development-only and rebuilt often.
        return

    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("products"):
        if set(constraint.get("column_names") or []) == {"url"}:
            op.drop_constraint(constraint["name"], "products", type_="unique")
            break
    op.create_unique_constraint(
        "uq_products_user_url",
        "products",
        ["user_id", "url"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.drop_constraint("uq_products_user_url", "products", type_="unique")
    op.create_unique_constraint("products_url_key", "products", ["url"])
