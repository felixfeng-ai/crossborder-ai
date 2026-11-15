"""create marketing image suites and platform items

Revision ID: 048_marketing_image_suites
Revises: 047_image_generation_modes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "048_marketing_image_suites"
down_revision: Union[str, None] = "047_image_generation_modes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketing_image_suites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketing_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "direction",
            sa.String(length=40),
            nullable=False,
            server_default="conversion",
        ),
        sa.Column(
            "theme",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "quality_tier",
            sa.String(length=20),
            nullable=False,
            server_default="fast",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "total_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_marketing_image_suites_user_idempotency",
        ),
    )
    op.create_index(
        "ix_marketing_image_suites_user_id",
        "marketing_image_suites",
        ["user_id"],
    )
    op.create_index(
        "ix_marketing_image_suites_campaign_id",
        "marketing_image_suites",
        ["campaign_id"],
    )
    op.create_index(
        "ix_marketing_image_suites_status",
        "marketing_image_suites",
        ["status"],
    )

    op.create_table(
        "marketing_image_suite_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "suite_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketing_image_suites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("preset_id", sa.String(length=50), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=12), nullable=False),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "image_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("image_generation_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "suite_id",
            "platform",
            name="uq_marketing_image_suite_items_platform",
        ),
    )
    op.create_index(
        "ix_marketing_image_suite_items_suite_id",
        "marketing_image_suite_items",
        ["suite_id"],
    )
    op.create_index(
        "ix_marketing_image_suite_items_image_task_id",
        "marketing_image_suite_items",
        ["image_task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketing_image_suite_items_image_task_id",
        table_name="marketing_image_suite_items",
    )
    op.drop_index(
        "ix_marketing_image_suite_items_suite_id",
        table_name="marketing_image_suite_items",
    )
    op.drop_table("marketing_image_suite_items")
    op.drop_index(
        "ix_marketing_image_suites_status",
        table_name="marketing_image_suites",
    )
    op.drop_index(
        "ix_marketing_image_suites_campaign_id",
        table_name="marketing_image_suites",
    )
    op.drop_index(
        "ix_marketing_image_suites_user_id",
        table_name="marketing_image_suites",
    )
    op.drop_table("marketing_image_suites")
