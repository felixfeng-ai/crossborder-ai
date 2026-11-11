"""create marketing video projects and shots

Revision ID: 021_marketing_video_projects
Revises: 020_video_generation_tasks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "021_marketing_video_projects"
down_revision: Union[str, None] = "020_video_generation_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketing_video_projects",
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
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("market", sa.String(50), nullable=False, server_default="US"),
        sa.Column("language", sa.String(30), nullable=False, server_default="en"),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("resolution", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="brief_ready",
        ),
        sa.Column("brief_json", sa.Text(), nullable=False),
        sa.Column("credits_estimated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_storage_key", sa.String(500), nullable=True),
        sa.Column("mime", sa.String(100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
            name="uq_marketing_video_user_idempotency",
        ),
    )
    op.create_table(
        "marketing_video_shots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketing_video_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.Column(
            "video_task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("video_generation_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "position",
            name="uq_marketing_video_shot_position",
        ),
    )
    op.create_index(
        "ix_marketing_video_projects_user_id",
        "marketing_video_projects",
        ["user_id"],
    )
    op.create_index(
        "ix_marketing_video_projects_source_asset_id",
        "marketing_video_projects",
        ["source_asset_id"],
    )
    op.create_index(
        "ix_marketing_video_projects_status",
        "marketing_video_projects",
        ["status"],
    )
    op.create_index(
        "ix_marketing_video_shots_project_id",
        "marketing_video_shots",
        ["project_id"],
    )
    op.create_index(
        "ix_marketing_video_shots_status",
        "marketing_video_shots",
        ["status"],
    )
    op.create_index(
        "ix_marketing_video_shots_video_task_id",
        "marketing_video_shots",
        ["video_task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_video_shots_video_task_id",
        table_name="marketing_video_shots",
    )
    op.drop_index(
        "ix_marketing_video_shots_status",
        table_name="marketing_video_shots",
    )
    op.drop_index(
        "ix_marketing_video_shots_project_id",
        table_name="marketing_video_shots",
    )
    op.drop_index(
        "ix_marketing_video_projects_status",
        table_name="marketing_video_projects",
    )
    op.drop_index(
        "ix_marketing_video_projects_source_asset_id",
        table_name="marketing_video_projects",
    )
    op.drop_index(
        "ix_marketing_video_projects_user_id",
        table_name="marketing_video_projects",
    )
    op.drop_table("marketing_video_shots")
    op.drop_table("marketing_video_projects")
