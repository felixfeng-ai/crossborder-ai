"""回填历史业务数据的个人工作区归属。

Revision ID: 075_workspace_history_backfill
Revises: 074_agent_workspace_idem
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "075_workspace_history_backfill"
down_revision: Union[str, None] = "074_agent_workspace_idem"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 同一用户在升级前通常只有个人工作区；这里覆盖所有已引入 workspace_id
# 的业务表，修复旧迁移因列已存在而跳过回填的历史数据。
BACKFILL_TABLES = {
    "products": "user_id",
    "product_variants": "user_id",
    "listing_drafts": "user_id",
    "listings": "owner_id",
    "image_assets": "user_id",
    "audio_assets": "user_id",
    "shopify_channels": "user_id",
    "image_generation_tasks": "user_id",
    "video_generation_tasks": "user_id",
    "marketing_campaigns": "user_id",
    "marketing_copy_assets": "user_id",
    "marketing_image_suites": "user_id",
    "marketing_video_projects": "user_id",
    "marketing_campaign_publications": "user_id",
    "marketing_performance_snapshots": "user_id",
    "personas": "user_id",
    "content_generations": "user_id",
    "batch_jobs": "user_id",
    "store_check_logs": "user_id",
    "operation_alerts": "user_id",
    "variant_snapshots": "user_id",
    "publications": "user_id",
    "voc_analyses": "user_id",
    "agent_tasks": "user_id",
    "conversations": "user_id",
}


def _backfill_table(table_name: str, owner_column: str) -> None:
    """只回填能唯一确定个人工作区的数据，不猜测团队归属。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }
    if "workspace_id" not in columns or owner_column not in columns:
        return

    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET workspace_id = (
                SELECT workspaces.id
                FROM workspaces
                WHERE workspaces.owner_user_id = {table_name}.{owner_column}
                  AND workspaces.type = 'personal'
                ORDER BY
                    CASE WHEN workspaces.status = 'active' THEN 0 ELSE 1 END,
                    workspaces.created_at,
                    workspaces.id
                LIMIT 1
            )
            WHERE workspace_id IS NULL
              AND {owner_column} IS NOT NULL
            """
        )
    )


def upgrade() -> None:
    for table_name, owner_column in BACKFILL_TABLES.items():
        _backfill_table(table_name, owner_column)


def downgrade() -> None:
    # 归属是历史数据的事实修复；回滚结构时不擦除已确认的工作区归属。
    pass
