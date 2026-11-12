"""add video continuity and product reference assets

Revision ID: 032_video_continuity_engine
Revises: 031_pricing_campaign
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "032_video_continuity_engine"
down_revision: Union[str, None] = "031_pricing_campaign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_generation_tasks",
        sa.Column(
            "reference_assets_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "marketing_video_projects",
        sa.Column(
            "reference_assets_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("marketing_video_projects", "reference_assets_json")
    op.drop_column("video_generation_tasks", "reference_assets_json")
