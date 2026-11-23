"""add user deletion and workspace lifecycle ownership

Revision ID: 072_user_workspace_lifecycle
Revises: 071_customer_order_links
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "072_user_workspace_lifecycle"
down_revision: Union[str, None] = "071_customer_order_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}

ADDED_WORKSPACE_TABLES = {
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

EXISTING_WORKSPACE_TABLES = {
    "products": "user_id",
    "product_variants": "user_id",
    "listing_drafts": "user_id",
    "listings": "owner_id",
    "image_assets": "user_id",
    "audio_assets": "user_id",
    "shopify_channels": "user_id",
    "action_approvals": "user_id",
    "work_item_commands": "actor_user_id",
}

WORKSPACE_CASCADE_TABLES = {
    "products",
    "product_variants",
    "listing_drafts",
    "listings",
    "image_assets",
    "audio_assets",
    "shopify_channels",
    *ADDED_WORKSPACE_TABLES,
}


def _uuid_type():
    return postgresql.UUID(as_uuid=True)


def _foreign_keys(table_name: str) -> list[dict]:
    return sa.inspect(op.get_bind()).get_foreign_keys(table_name)


def _drop_matching_fk(table_name: str, column: str) -> None:
    """删除指定列上的用户外键；SQLite 未命名约束走 batch 命名规则。"""

    if op.get_bind().dialect.name == "postgresql":
        for foreign_key in _foreign_keys(table_name):
            if foreign_key["constrained_columns"] == [column]:
                name = foreign_key.get("name")
                if name:
                    op.drop_constraint(
                        name,
                        table_name,
                        type_="foreignkey",
                    )
                return


def _replace_user_fk(
    table_name: str,
    column: str,
    *,
    nullable: bool = True,
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    columns = {
        item["name"]
        for item in inspector.get_columns(table_name)
    }
    if column not in columns:
        # 历史漂移库可能缺少该归属列，由后续 schema repair 补齐；
        # 此处不能对不存在的列执行 batch.alter_column。
        return
    if bind.dialect.name == "postgresql":
        _drop_matching_fk(table_name, column)
        op.alter_column(
            table_name,
            column,
            existing_type=_uuid_type(),
            nullable=nullable,
        )
        op.create_foreign_key(
            f"fk_{table_name}_{column}_users",
            table_name,
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )
        return

    column_info = next(
        item for item in inspector.get_columns(table_name)
        if item["name"] == column
    )
    if bool(column_info.get("nullable", True)) == nullable:
        return
    existing_tables = set(inspector.get_table_names())
    if any(
        foreign_key.get("referred_table") not in existing_tables
        for foreign_key in inspector.get_foreign_keys(table_name)
    ):
        # SQLite 历史漂移库可能缺少被引用表；batch 重建无法安全反射
        # 不存在的父表。真实 PostgreSQL 仍会执行完整 FK 替换。
        return
    with op.batch_alter_table(
        table_name,
        naming_convention=FK_NAMING_CONVENTION,
        recreate="always",
    ) as batch:
        batch.alter_column(
            column,
            existing_type=_uuid_type(),
            nullable=nullable,
        )


def _replace_workspace_fk(
    table_name: str,
    *,
    nullable: bool = True,
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    columns = {
        item["name"]
        for item in inspector.get_columns(table_name)
    }
    if "workspace_id" not in columns:
        return
    if bind.dialect.name == "postgresql":
        for foreign_key in _foreign_keys(table_name):
            if foreign_key["constrained_columns"] == ["workspace_id"]:
                name = foreign_key.get("name")
                if name:
                    op.drop_constraint(
                        name,
                        table_name,
                        type_="foreignkey",
                    )
                break
        op.alter_column(
            table_name,
            "workspace_id",
            existing_type=_uuid_type(),
            nullable=nullable,
        )
        op.create_foreign_key(
            f"fk_{table_name}_workspace_id_workspaces",
            table_name,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        return

    column_info = next(
        item for item in inspector.get_columns(table_name)
        if item["name"] == "workspace_id"
    )
    if bool(column_info.get("nullable", True)) == nullable:
        return
    existing_tables = set(inspector.get_table_names())
    if any(
        foreign_key.get("referred_table") not in existing_tables
        for foreign_key in inspector.get_foreign_keys(table_name)
    ):
        return
    with op.batch_alter_table(
        table_name,
        naming_convention=FK_NAMING_CONVENTION,
        recreate="always",
    ) as batch:
        batch.alter_column(
            "workspace_id",
            existing_type=_uuid_type(),
            nullable=nullable,
        )


def _add_workspace_scope(table_name: str, owner_column: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return
    existing_tables = set(inspector.get_table_names())
    if any(
        foreign_key.get("referred_table") not in existing_tables
        for foreign_key in inspector.get_foreign_keys(table_name)
    ):
        return
    columns = {
        item["name"] for item in inspector.get_columns(table_name)
    }
    if owner_column not in columns or "workspace_id" in columns:
        return
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(
            sa.Column(
                "workspace_id",
                _uuid_type(),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            f"fk_{table_name}_workspace_id_workspaces",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index(
        f"ix_{table_name}_workspace_id",
        table_name,
        ["workspace_id"],
    )
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
                    workspaces.created_at
                LIMIT 1
            )
            WHERE workspace_id IS NULL
              AND {owner_column} IS NOT NULL
            """
        )
    )


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "deletion_reason",
                sa.String(length=80),
                nullable=True,
            )
        )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    if op.get_bind().dialect.name == "postgresql":
        _drop_matching_fk("workspaces", "owner_user_id")

    with op.batch_alter_table("workspaces") as batch:
        batch.alter_column(
            "owner_user_id",
            existing_type=_uuid_type(),
            nullable=True,
        )
        batch.add_column(
            sa.Column(
                "archived_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "purge_after",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "archived_by_user_id",
                _uuid_type(),
                nullable=True,
            )
        )
        if op.get_bind().dialect.name == "postgresql":
            batch.create_foreign_key(
                "fk_workspaces_owner_user_id_users",
                "users",
                ["owner_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_foreign_key(
                "fk_workspaces_archived_by_user_id_users",
                "users",
                ["archived_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
        else:
            batch.create_foreign_key(
                "fk_workspaces_archived_by_user_id_users",
                "users",
                ["archived_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
    op.create_index(
        "ix_workspaces_purge_after",
        "workspaces",
        ["purge_after"],
    )
    op.create_index(
        "ix_workspaces_archived_by_user_id",
        "workspaces",
        ["archived_by_user_id"],
    )

    for table_name, owner_column in {
        **EXISTING_WORKSPACE_TABLES,
        **ADDED_WORKSPACE_TABLES,
    }.items():
        _replace_user_fk(table_name, owner_column)

    for table_name, owner_column in ADDED_WORKSPACE_TABLES.items():
        _add_workspace_scope(table_name, owner_column)

    for table_name in (
        "products",
        "product_variants",
        "listing_drafts",
        "listings",
        "image_assets",
        "shopify_channels",
    ):
        _replace_workspace_fk(table_name)


def downgrade() -> None:
    op.drop_index(
        "ix_workspaces_archived_by_user_id",
        table_name="workspaces",
    )
    op.drop_index("ix_workspaces_purge_after", table_name="workspaces")
    op.drop_index("ix_users_deleted_at", table_name="users")

    for table_name in ADDED_WORKSPACE_TABLES:
        op.drop_index(
            f"ix_{table_name}_workspace_id",
            table_name=table_name,
        )
        with op.batch_alter_table(table_name) as batch:
            batch.drop_column("workspace_id")

    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("archived_by_user_id")
        batch.drop_column("purge_after")
        batch.drop_column("archived_at")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("deletion_reason")
        batch.drop_column("deleted_at")
