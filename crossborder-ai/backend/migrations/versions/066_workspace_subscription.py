"""scope plan upgrade requests to workspaces

Revision ID: 066_workspace_subscription
Revises: 065_mobile_audio_assets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "066_workspace_subscription"
down_revision: Union[str, None] = "065_mobile_audio_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "plan_upgrade_requests" not in sa.inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table("plan_upgrade_requests") as batch:
        batch.add_column(
            sa.Column(
                "workspace_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "created_by_user_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_plan_upgrade_requests_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_plan_upgrade_requests_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_plan_upgrade_requests_workspace_id",
            ["workspace_id"],
        )
        batch.create_index(
            "ix_plan_upgrade_requests_created_by_user_id",
            ["created_by_user_id"],
        )


def downgrade() -> None:
    if "plan_upgrade_requests" not in sa.inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table("plan_upgrade_requests") as batch:
        batch.drop_index("ix_plan_upgrade_requests_created_by_user_id")
        batch.drop_index("ix_plan_upgrade_requests_workspace_id")
        batch.drop_constraint(
            "fk_plan_upgrade_requests_created_by_user_id",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_plan_upgrade_requests_workspace_id",
            type_="foreignkey",
        )
        batch.drop_column("created_by_user_id")
        batch.drop_column("workspace_id")
