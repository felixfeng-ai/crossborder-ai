"""add image generation modes and provider audit fields

Revision ID: 047_image_generation_modes
Revises: 046_admin_operations
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "047_image_generation_modes"
down_revision: Union[str, None] = "046_admin_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 存量任务统一标记为 legacy，确保旧客户端仍按每张 3 积分解释。
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "mode",
            sa.String(length=32),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column("quality_tier", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "provider",
            sa.String(length=24),
            nullable=False,
            server_default="auto",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column("resolution", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column("aspect_ratio", sa.String(length=12), nullable=True),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column("negative_prompt", sa.Text(), nullable=True),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column("style_preset", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "use_brand_persona",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "reference_assets_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "reference_coverage",
            sa.String(length=24),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "generation_params_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "estimated_cost_micros",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "actual_cost_micros",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "parent_task_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "image_generation_tasks",
        sa.Column(
            "next_poll_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_image_generation_tasks_mode",
        "image_generation_tasks",
        ["mode"],
    )
    op.create_index(
        "ix_image_generation_tasks_parent_task_id",
        "image_generation_tasks",
        ["parent_task_id"],
    )
    # SQLite 不支持直接 ALTER CONSTRAINT；batch 模式会安全重建表，
    # PostgreSQL 则仍生成标准的 ALTER TABLE。
    with op.batch_alter_table("image_generation_tasks") as batch_op:
        batch_op.create_unique_constraint(
            "uq_image_generation_tasks_user_idempotency",
            ["user_id", "idempotency_key"],
        )
        batch_op.create_foreign_key(
            "fk_image_generation_tasks_parent_task_id",
            "image_generation_tasks",
            ["parent_task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("image_generation_tasks") as batch_op:
        batch_op.drop_constraint(
            "fk_image_generation_tasks_parent_task_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "uq_image_generation_tasks_user_idempotency",
            type_="unique",
        )
    op.drop_index(
        "ix_image_generation_tasks_parent_task_id",
        table_name="image_generation_tasks",
    )
    op.drop_index(
        "ix_image_generation_tasks_mode",
        table_name="image_generation_tasks",
    )
    for column in (
        "next_poll_at",
        "parent_task_id",
        "idempotency_key",
        "actual_cost_micros",
        "estimated_cost_micros",
        "generation_params_json",
        "reference_coverage",
        "reference_assets_json",
        "use_brand_persona",
        "style_preset",
        "negative_prompt",
        "aspect_ratio",
        "resolution",
        "provider",
        "quality_tier",
        "mode",
    ):
        op.drop_column("image_generation_tasks", column)
