"""add marketing video provider snapshot

Revision ID: 035_video_provider_abstraction
Revises: 034_own_supply_products
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "035_video_provider_abstraction"
down_revision: Union[str, None] = "034_own_supply_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "marketing_video_projects",
        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
            server_default="minimax",
        ),
    )
    op.create_index(
        "ix_marketing_video_projects_provider",
        "marketing_video_projects",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_video_projects_provider",
        table_name="marketing_video_projects",
    )
    op.drop_column("marketing_video_projects", "provider")
