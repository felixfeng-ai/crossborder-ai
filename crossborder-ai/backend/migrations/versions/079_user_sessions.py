"""create revocable user sessions

Revision ID: 079_user_sessions
Revises: 078_workspace_monitor_settings
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "079_user_sessions"
down_revision: Union[str, None] = "078_workspace_monitor_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type():
    return (
        postgresql.UUID(as_uuid=True)
        if op.get_bind().dialect.name == "postgresql"
        else sa.String(36)
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("user_sessions"):
        return
    op.create_table(
        "user_sessions",
        sa.Column("id", _uuid_type(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid_type(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "refresh_token_hash",
            sa.String(64),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "previous_refresh_token_hash",
            sa.String(64),
            nullable=True,
        ),
        sa.Column("device_name", sa.String(120), nullable=True),
        sa.Column("platform", sa.String(40), nullable=True),
        sa.Column("client_version", sa.String(40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("revoke_reason", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_user_sessions_user_id",
        "user_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_user_sessions_refresh_token_hash",
        "user_sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_user_sessions_previous_refresh_token_hash",
        "user_sessions",
        ["previous_refresh_token_hash"],
    )
    op.create_index(
        "ix_user_sessions_expires_at",
        "user_sessions",
        ["expires_at"],
    )
    op.create_index(
        "ix_user_sessions_revoked_at",
        "user_sessions",
        ["revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index(
        "ix_user_sessions_previous_refresh_token_hash",
        table_name="user_sessions",
    )
    op.drop_index(
        "ix_user_sessions_refresh_token_hash",
        table_name="user_sessions",
    )
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
