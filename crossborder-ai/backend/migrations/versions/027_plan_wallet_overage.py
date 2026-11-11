"""add plan wallets, subscriptions, usage quotas and credit purchases

Revision ID: 027_plan_wallet_overage
Revises: 026_video_credit_refunds
"""

from datetime import datetime, timedelta, timezone
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "027_plan_wallet_overage"
down_revision: Union[str, None] = "026_video_credit_refunds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    bind = op.get_bind()
    return sa.String(36) if bind.dialect.name == "sqlite" else postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    transaction_columns = {
        item["name"] for item in inspector.get_columns("credit_transactions")
    }
    if "wallet_type" not in transaction_columns:
        op.add_column(
            "credit_transactions",
            sa.Column("wallet_type", sa.String(length=20), nullable=True),
        )

    op.create_table(
        "credit_wallets",
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("plan_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchased_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_credit_wallets_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "user_subscriptions",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual_transfer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_subscriptions_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
    op.create_index("ix_user_subscriptions_plan", "user_subscriptions", ["plan"])
    op.create_index("ix_user_subscriptions_status", "user_subscriptions", ["status"])
    op.create_index("ix_user_subscriptions_expires_at", "user_subscriptions", ["expires_at"])

    op.create_table(
        "feature_usage_counters",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_feature_usage_counters_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "feature",
            "period_key",
            name="uq_feature_usage_user_feature_period",
        ),
    )
    op.create_index("ix_feature_usage_counters_user_id", "feature_usage_counters", ["user_id"])
    op.create_index("ix_feature_usage_counters_feature", "feature_usage_counters", ["feature"])
    op.create_index("ix_feature_usage_counters_period_key", "feature_usage_counters", ["period_key"])

    op.create_table(
        "credit_purchases",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("user_id", _uuid_type(), nullable=False),
        sa.Column("pack_id", sa.String(length=32), nullable=False),
        sa.Column("pack_name", sa.String(length=100), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("contact", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("handled_by", _uuid_type(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_credit_purchases_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_credit_purchases_order_id"),
    )
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"])
    op.create_index("ix_credit_purchases_status", "credit_purchases", ["status"])
    op.create_index("ix_credit_purchases_order_id", "credit_purchases", ["order_id"], unique=True)

    bind.execute(
        sa.text(
            """
            INSERT INTO credit_wallets (user_id, plan_credits, purchased_credits)
            SELECT id, credits, 0 FROM users
            WHERE id NOT IN (SELECT user_id FROM credit_wallets)
            """
        )
    )

    users = bind.execute(
        sa.text("SELECT id, plan FROM users WHERE plan IN ('standard', 'professional')")
    ).mappings().all()
    now = datetime.now(timezone.utc)
    subscriptions = sa.Table(
        "user_subscriptions",
        sa.MetaData(),
        autoload_with=bind,
    )
    if users:
        id_value = (lambda: str(uuid.uuid4())) if bind.dialect.name == "sqlite" else (lambda: uuid.uuid4())
        bind.execute(
            subscriptions.insert(),
            [
                {
                    "id": id_value(),
                    "user_id": row["id"],
                    "plan": row["plan"],
                    "status": "active",
                    "starts_at": now,
                    "expires_at": now + timedelta(days=30),
                    "source": "migration_grandfather",
                }
                for row in users
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_credit_purchases_order_id", table_name="credit_purchases")
    op.drop_index("ix_credit_purchases_status", table_name="credit_purchases")
    op.drop_index("ix_credit_purchases_user_id", table_name="credit_purchases")
    op.drop_table("credit_purchases")
    op.drop_index("ix_feature_usage_counters_period_key", table_name="feature_usage_counters")
    op.drop_index("ix_feature_usage_counters_feature", table_name="feature_usage_counters")
    op.drop_index("ix_feature_usage_counters_user_id", table_name="feature_usage_counters")
    op.drop_table("feature_usage_counters")
    op.drop_index("ix_user_subscriptions_expires_at", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_status", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_plan", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_user_id", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
    op.drop_table("credit_wallets")
    with op.batch_alter_table("credit_transactions") as batch:
        batch.drop_column("wallet_type")
