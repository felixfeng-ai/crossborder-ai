"""add workspace billing core

Revision ID: 064_workspace_billing_core
Revises: 063_workspace_listing_scope
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "064_workspace_billing_core"
down_revision: Union[str, None] = "063_workspace_listing_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_credit_wallets",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "plan_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "purchased_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "workspace_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "payer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="manual_transfer",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    for column_name in ("workspace_id", "plan", "status", "expires_at", "payer_user_id"):
        op.create_index(
            f"ix_workspace_subscriptions_{column_name}",
            "workspace_subscriptions",
            [column_name],
        )

    inspector = sa.inspect(op.get_bind())
    if "credit_transactions" in inspector.get_table_names():
        with op.batch_alter_table("credit_transactions") as batch:
            batch.add_column(
                sa.Column(
                    "workspace_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                )
            )
            batch.add_column(
                sa.Column(
                    "actor_user_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                )
            )
            batch.create_foreign_key(
                "fk_credit_transactions_workspace_id",
                "workspaces",
                ["workspace_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_foreign_key(
                "fk_credit_transactions_actor_user_id",
                "users",
                ["actor_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index(
                "ix_credit_transactions_workspace_id",
                ["workspace_id"],
            )
            batch.create_index(
                "ix_credit_transactions_actor_user_id",
                ["actor_user_id"],
            )

    if "credit_purchases" in inspector.get_table_names():
        with op.batch_alter_table("credit_purchases") as batch:
            batch.add_column(
                sa.Column(
                    "workspace_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                )
            )
            batch.add_column(
                sa.Column(
                    "created_by_user_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                )
            )
            batch.create_foreign_key(
                "fk_credit_purchases_workspace_id",
                "workspaces",
                ["workspace_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_foreign_key(
                "fk_credit_purchases_created_by_user_id",
                "users",
                ["created_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index(
                "ix_credit_purchases_workspace_id",
                ["workspace_id"],
            )
            batch.create_index(
                "ix_credit_purchases_created_by_user_id",
                ["created_by_user_id"],
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "credit_purchases" in inspector.get_table_names():
        with op.batch_alter_table("credit_purchases") as batch:
            batch.drop_index("ix_credit_purchases_created_by_user_id")
            batch.drop_index("ix_credit_purchases_workspace_id")
            batch.drop_constraint(
                "fk_credit_purchases_created_by_user_id",
                type_="foreignkey",
            )
            batch.drop_constraint(
                "fk_credit_purchases_workspace_id",
                type_="foreignkey",
            )
            batch.drop_column("created_by_user_id")
            batch.drop_column("workspace_id")

    if "credit_transactions" in inspector.get_table_names():
        with op.batch_alter_table("credit_transactions") as batch:
            batch.drop_index("ix_credit_transactions_actor_user_id")
            batch.drop_index("ix_credit_transactions_workspace_id")
            batch.drop_constraint(
                "fk_credit_transactions_actor_user_id",
                type_="foreignkey",
            )
            batch.drop_constraint(
                "fk_credit_transactions_workspace_id",
                type_="foreignkey",
            )
            batch.drop_column("actor_user_id")
            batch.drop_column("workspace_id")

    for column_name in reversed(
        ("workspace_id", "plan", "status", "expires_at", "payer_user_id")
    ):
        op.drop_index(
            f"ix_workspace_subscriptions_{column_name}",
            table_name="workspace_subscriptions",
        )
    op.drop_table("workspace_subscriptions")
    op.drop_table("workspace_credit_wallets")
