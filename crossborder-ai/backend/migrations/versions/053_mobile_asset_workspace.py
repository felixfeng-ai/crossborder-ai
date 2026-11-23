"""scope mobile assets to workspaces

Revision ID: 053_mobile_asset_workspace
Revises: 052_action_runtime
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "053_mobile_asset_workspace"
down_revision: Union[str, None] = "052_action_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """历史素材保持为空，新移动端上传必须携带工作区。"""

    # SQLite 不支持直接 ALTER 外键，batch 模式同时兼容本地测试和生产 PG。
    with op.batch_alter_table("image_assets") as batch:
        batch.add_column(
            sa.Column(
                "workspace_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_image_assets_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_image_assets_workspace_id",
            ["workspace_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("image_assets") as batch:
        batch.drop_index("ix_image_assets_workspace_id")
        batch.drop_constraint(
            "fk_image_assets_workspace_id",
            type_="foreignkey",
        )
        batch.drop_column("workspace_id")
