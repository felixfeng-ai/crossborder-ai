"""link media tasks to marketing campaigns

Revision ID: 038_campaign_assets
Revises: 037_marketing_campaigns
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "038_campaign_assets"
down_revision: Union[str, None] = "037_marketing_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in (
        "image_generation_tasks",
        "video_generation_tasks",
        "marketing_video_projects",
    ):
        op.add_column(
            table,
            sa.Column("campaign_id", UUID(as_uuid=True), nullable=True),
        )
        op.create_index(
            f"ix_{table}_campaign_id",
            table,
            ["campaign_id"],
        )


def downgrade() -> None:
    for table in (
        "marketing_video_projects",
        "video_generation_tasks",
        "image_generation_tasks",
    ):
        op.drop_index(
            f"ix_{table}_campaign_id",
            table_name=table,
        )
        op.drop_column(table, "campaign_id")
