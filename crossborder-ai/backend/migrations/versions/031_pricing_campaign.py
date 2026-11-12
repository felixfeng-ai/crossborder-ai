"""add campaign pricing audit fields

Revision ID: 031_pricing_campaign
Revises: 030_professional_storyboard
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "031_pricing_campaign"
down_revision: Union[str, None] = "030_professional_storyboard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "plan_upgrade_requests" not in tables:
        # 兼容历史 stamp 场景：旧迁移被跳过时，本次直接补回完整表。
        op.create_table(
            "plan_upgrade_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("plan", sa.String(length=20), nullable=False),
            sa.Column("contact", sa.String(length=100), nullable=False),
            sa.Column("order_id", sa.String(length=40), nullable=False, unique=True),
            sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "original_amount",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "billing_cycle",
                sa.String(length=20),
                nullable=False,
                server_default="monthly",
            ),
            sa.Column("promotion_code", sa.String(length=50), nullable=True),
            sa.Column(
                "bonus_credits",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "duration_days",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("handled_by", sa.String(length=36), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.Column(
                "handled_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_plan_upgrade_requests_user_id",
            "plan_upgrade_requests",
            ["user_id"],
        )
        op.create_index(
            "ix_plan_upgrade_requests_status",
            "plan_upgrade_requests",
            ["status"],
        )
    else:
        op.add_column(
            "plan_upgrade_requests",
            sa.Column(
                "original_amount",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
        op.add_column(
            "plan_upgrade_requests",
            sa.Column(
                "billing_cycle",
                sa.String(length=20),
                nullable=False,
                server_default="monthly",
            ),
        )
        op.add_column(
            "plan_upgrade_requests",
            sa.Column("promotion_code", sa.String(length=50), nullable=True),
        )
        op.add_column(
            "plan_upgrade_requests",
            sa.Column(
                "bonus_credits",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
        op.add_column(
            "plan_upgrade_requests",
            sa.Column(
                "duration_days",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
        )
        op.execute(
            "UPDATE plan_upgrade_requests "
            "SET original_amount = amount "
            "WHERE original_amount = 0"
        )

    with op.batch_alter_table("credit_purchases") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("credit_purchases") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "plan_upgrade_requests" in tables:
        op.drop_column("plan_upgrade_requests", "duration_days")
        op.drop_column("plan_upgrade_requests", "bonus_credits")
        op.drop_column("plan_upgrade_requests", "promotion_code")
        op.drop_column("plan_upgrade_requests", "billing_cycle")
        op.drop_column("plan_upgrade_requests", "original_amount")
