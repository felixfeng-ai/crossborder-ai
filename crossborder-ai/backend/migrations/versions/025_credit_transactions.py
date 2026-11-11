"""add credit ledger and monthly period

Revision ID: 025_credit_transactions
Revises: 024_shopify_compliance_events
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "025_credit_transactions"
down_revision: Union[str, None] = "024_shopify_compliance_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    bind = op.get_bind()
    return sa.String(36) if bind.dialect.name == "sqlite" else postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {item["name"] for item in inspector.get_columns("users")}
    if "credit_period_start" not in user_columns:
        op.add_column(
            "users",
            sa.Column("credit_period_start", sa.DateTime(timezone=True), nullable=True),
        )

    image_columns = {
        item["name"]
        for item in inspector.get_columns("image_generation_tasks")
    }
    if "credits_cost" not in image_columns:
        op.add_column(
            "image_generation_tasks",
            sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="0"),
        )
    if "credits_charged" not in image_columns:
        op.add_column(
            "image_generation_tasks",
            sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        )

    op.create_table(
        "credit_transactions",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=128), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_credit_transactions_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_credit_transactions_user_id",
        "credit_transactions",
        ["user_id"],
    )
    op.create_index(
        "ix_credit_transactions_feature",
        "credit_transactions",
        ["feature"],
    )
    op.create_index(
        "ix_credit_transactions_reference_id",
        "credit_transactions",
        ["reference_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_transactions_reference_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_feature", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")
    with op.batch_alter_table("image_generation_tasks") as batch:
        batch.drop_column("credits_charged")
        batch.drop_column("credits_cost")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("credit_period_start")
