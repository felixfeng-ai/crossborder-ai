"""add shared video quality and style snapshots

Revision ID: 033_video_quality_engine
Revises: 032_video_continuity_engine
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "033_video_quality_engine"
down_revision: Union[str, None] = "032_video_continuity_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_quality_columns(table_name: str, default_style: str) -> None:
    op.add_column(
        table_name,
        sa.Column(
            "quality_tier",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        table_name,
        sa.Column(
            "style_preset",
            sa.String(length=50),
            nullable=False,
            server_default=default_style,
        ),
    )
    op.add_column(
        table_name,
        sa.Column(
            "credits_per_second",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def upgrade() -> None:
    _add_quality_columns("marketing_video_projects", "premium_luxury")
    _add_quality_columns("video_generation_tasks", "commerce_showcase")


def downgrade() -> None:
    for table_name in (
        "video_generation_tasks",
        "marketing_video_projects",
    ):
        op.drop_column(table_name, "credits_per_second")
        op.drop_column(table_name, "style_preset")
        op.drop_column(table_name, "quality_tier")
