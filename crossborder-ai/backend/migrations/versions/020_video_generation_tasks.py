"""create AI video generation tasks

Revision ID: 020_video_generation_tasks
Revises: 019_operations_monitor
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "020_video_generation_tasks"
down_revision: Union[str, None] = "019_operations_monitor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_generation_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("image_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("template_id", sa.String(50), nullable=False, server_default="clean_product"),
        sa.Column("provider", sa.String(30), nullable=False, server_default="minimax"),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("resolution", sa.String(20), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("ratio", sa.String(20), nullable=False, server_default="9:16"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("provider_task_id", sa.String(255), nullable=True),
        sa.Column("provider_status", sa.String(50), nullable=True),
        sa.Column("remote_video_url", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("mime", sa.String(100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("poll_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_video_tasks_user_idempotency",
        ),
    )
    op.create_index("ix_video_generation_tasks_user_id", "video_generation_tasks", ["user_id"])
    op.create_index("ix_video_generation_tasks_source_asset_id", "video_generation_tasks", ["source_asset_id"])
    op.create_index("ix_video_generation_tasks_status", "video_generation_tasks", ["status"])
    op.create_index("ix_video_generation_tasks_provider_task_id", "video_generation_tasks", ["provider_task_id"])
    op.create_index("ix_video_generation_tasks_next_poll_at", "video_generation_tasks", ["next_poll_at"])


def downgrade() -> None:
    op.drop_index("ix_video_generation_tasks_next_poll_at", table_name="video_generation_tasks")
    op.drop_index("ix_video_generation_tasks_provider_task_id", table_name="video_generation_tasks")
    op.drop_index("ix_video_generation_tasks_status", table_name="video_generation_tasks")
    op.drop_index("ix_video_generation_tasks_source_asset_id", table_name="video_generation_tasks")
    op.drop_index("ix_video_generation_tasks_user_id", table_name="video_generation_tasks")
    op.drop_table("video_generation_tasks")
