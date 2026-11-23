"""create mobile audio assets

Revision ID: 065_mobile_audio_assets
Revises: 064_workspace_billing_core
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "065_mobile_audio_assets"
down_revision: Union[str, None] = "064_workspace_billing_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audio_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("detected_language", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ready",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "idempotency_key",
            name="uq_audio_assets_workspace_user_idempotency",
        ),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_audio_assets_user_id", "audio_assets", ["user_id"])
    op.create_index(
        "ix_audio_assets_workspace_id",
        "audio_assets",
        ["workspace_id"],
    )
    op.create_index("ix_audio_assets_status", "audio_assets", ["status"])
    op.create_index(
        "ix_audio_assets_expires_at",
        "audio_assets",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audio_assets_expires_at", table_name="audio_assets")
    op.drop_index("ix_audio_assets_status", table_name="audio_assets")
    op.drop_index("ix_audio_assets_workspace_id", table_name="audio_assets")
    op.drop_index("ix_audio_assets_user_id", table_name="audio_assets")
    op.drop_table("audio_assets")
