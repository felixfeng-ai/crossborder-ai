"""add integration event retry and dead-letter fields

Revision ID: 061_integration_event_retry
Revises: 060_integration_events
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "061_integration_event_retry"
down_revision: Union[str, None] = "060_integration_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("integration_events") as batch:
        batch.add_column(
            sa.Column(
                "attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "max_attempts",
                sa.Integer(),
                nullable=False,
                server_default="5",
            )
        )
        batch.add_column(
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "processed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.create_index(
            "ix_integration_events_available_at",
            ["available_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("integration_events") as batch:
        batch.drop_index("ix_integration_events_available_at")
        batch.drop_column("processed_at")
        batch.drop_column("available_at")
        batch.drop_column("max_attempts")
        batch.drop_column("attempts")
