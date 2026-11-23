"""scope Shopify channels to workspaces

Revision ID: 059_shopify_channel_workspace
Revises: 058_agent_signals
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "059_shopify_channel_workspace"
down_revision: Union[str, None] = "058_agent_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "shopify_channels" not in inspector.get_table_names():
        # 历史 stamp 数据库可能缺少整张渠道表，不能用 ALTER 修补。
        op.create_table(
            "shopify_channels",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("shop_name", sa.String(length=255), nullable=False),
            sa.Column("access_token", sa.Text(), nullable=False),
            sa.Column("shop_domain", sa.String(length=255), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default="1",
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
        op.create_index(
            "ix_shopify_channels_user_id",
            "shopify_channels",
            ["user_id"],
        )
        op.create_index(
            "ix_shopify_channels_workspace_id",
            "shopify_channels",
            ["workspace_id"],
        )
        return
    with op.batch_alter_table("shopify_channels") as batch:
        batch.add_column(
            sa.Column(
                "workspace_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_shopify_channels_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_shopify_channels_workspace_id",
            ["workspace_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("shopify_channels") as batch:
        batch.drop_index("ix_shopify_channels_workspace_id")
        batch.drop_constraint(
            "fk_shopify_channels_workspace_id",
            type_="foreignkey",
        )
        batch.drop_column("workspace_id")
