"""create VOC analyses

Revision ID: 028_voc_analyses
Revises: 027_plan_wallet_overage
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "028_voc_analyses"
down_revision: Union[str, None] = "027_plan_wallet_overage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    bind = op.get_bind()
    return sa.String(36) if bind.dialect.name == "sqlite" else postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "voc_analyses",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("product_id", _uuid_type(), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=False, server_default="amazon"),
        sa.Column("language", sa.String(length=20), nullable=False, server_default="en"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("pain_points_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("selling_points_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("objections_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("keywords_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sentiment_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("recommendations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("model_used", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voc_analyses_user_id", "voc_analyses", ["user_id"])
    op.create_index("ix_voc_analyses_product_id", "voc_analyses", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_voc_analyses_product_id", table_name="voc_analyses")
    op.drop_index("ix_voc_analyses_user_id", table_name="voc_analyses")
    op.drop_table("voc_analyses")
