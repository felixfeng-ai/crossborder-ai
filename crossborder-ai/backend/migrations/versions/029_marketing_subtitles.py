"""add marketing subtitle status

Revision ID: 029_marketing_subtitles
Revises: 028_voc_analyses
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "029_marketing_subtitles"
down_revision: Union[str, None] = "028_voc_analyses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "marketing_video_projects",
        sa.Column(
            "subtitles_burned_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("marketing_video_projects", "subtitles_burned_in")
