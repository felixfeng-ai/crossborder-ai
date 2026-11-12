"""add marketing campaign context

Revision ID: 037_marketing_campaigns
Revises: 036_agent_workspace
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "037_marketing_campaigns"
down_revision: Union[str, None] = "036_agent_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_campaign_id",
        "conversations",
        ["campaign_id"],
    )
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "objective",
            sa.String(length=50),
            nullable=False,
            server_default="conversion",
        ),
        sa.Column(
            "platform",
            sa.String(length=50),
            nullable=False,
            server_default="tiktok",
        ),
        sa.Column(
            "market",
            sa.String(length=50),
            nullable=False,
            server_default="US",
        ),
        sa.Column(
            "language",
            sa.String(length=20),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="planning",
        ),
        sa.Column(
            "budget_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "spent_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "brief_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_marketing_campaigns_user_id",
        "marketing_campaigns",
        ["user_id"],
    )
    op.create_index(
        "ix_marketing_campaigns_product_id",
        "marketing_campaigns",
        ["product_id"],
    )
    op.create_index(
        "ix_marketing_campaigns_status",
        "marketing_campaigns",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_campaigns_status",
        table_name="marketing_campaigns",
    )
    op.drop_index(
        "ix_marketing_campaigns_product_id",
        table_name="marketing_campaigns",
    )
    op.drop_index(
        "ix_marketing_campaigns_user_id",
        table_name="marketing_campaigns",
    )
    op.drop_table("marketing_campaigns")
    op.drop_index(
        "ix_conversations_campaign_id",
        table_name="conversations",
    )
    op.drop_column("conversations", "campaign_id")
