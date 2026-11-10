"""create user platform authorization connections

Revision ID: 015_platform_connections
Revises: 014_publications
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "015_platform_connections"
down_revision: Union[str, None] = "014_publications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=False),
        sa.Column("marketplace_id", sa.String(100), nullable=True),
        sa.Column("credentials", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id",
            "platform",
            "external_account_id",
            name="uq_platform_connections_account",
        ),
    )
    op.create_index("ix_platform_connections_user_id", "platform_connections", ["user_id"])
    op.create_index("ix_platform_connections_platform", "platform_connections", ["platform"])


def downgrade() -> None:
    op.drop_index("ix_platform_connections_platform", table_name="platform_connections")
    op.drop_index("ix_platform_connections_user_id", table_name="platform_connections")
    op.drop_table("platform_connections")
