"""add professional storyboard fields

Revision ID: 030_professional_storyboard
Revises: 029_marketing_subtitles
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "030_professional_storyboard"
down_revision: Union[str, None] = "029_marketing_subtitles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "marketing_video_projects",
        sa.Column(
            "mode",
            sa.String(length=20),
            nullable=False,
            server_default="creative",
        ),
    )
    op.add_column(
        "marketing_video_projects",
        sa.Column("script_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "marketing_video_projects",
        sa.Column(
            "continuity_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_marketing_video_projects_mode",
        "marketing_video_projects",
        ["mode"],
    )
    op.add_column(
        "marketing_video_shots",
        sa.Column("source_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marketing_video_shots", "source_text")
    op.drop_index(
        "ix_marketing_video_projects_mode",
        table_name="marketing_video_projects",
    )
    op.drop_column("marketing_video_projects", "continuity_json")
    op.drop_column("marketing_video_projects", "script_text")
    op.drop_column("marketing_video_projects", "mode")
