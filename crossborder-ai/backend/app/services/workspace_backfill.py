"""业务表工作区字段回填。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.listing import Listing
from app.models.listing_draft import ListingDraft
from app.models.workspace import Workspace


SCOPED_MODELS = {
    "products": (Product, "user_id"),
    "product_variants": (ProductVariant, "user_id"),
    "listing_drafts": (ListingDraft, "user_id"),
    "listings": (Listing, "owner_id"),
}
async def _backfill_table(
    db: AsyncSession,
    *,
    table_name: str,
    batch_size: int,
    dry_run: bool,
) -> dict[str, int]:
    model, owner_field = SCOPED_MODELS[table_name]
    cursor: UUID | None = None
    checked = 0
    eligible = 0
    unresolved = 0

    while True:
        query = (
            select(model)
            .where(model.workspace_id.is_(None))
            .order_by(model.id)
            .limit(batch_size)
        )
        if cursor is not None:
            query = query.where(model.id > cursor)
        rows = (await db.execute(query)).scalars().all()
        if not rows:
            break

        checked += len(rows)
        cursor = rows[-1].id
        user_ids = {
            getattr(row, owner_field)
            for row in rows
            if getattr(row, owner_field, None) is not None
        }
        workspaces = (
            (
                await db.execute(
                    select(Workspace).where(
                        Workspace.type == "personal",
                        Workspace.status == "active",
                        Workspace.owner_user_id.in_(user_ids),
                    )
                )
            )
            .scalars()
            .all()
            if user_ids
            else []
        )
        by_owner = {
            workspace.owner_user_id: workspace
            for workspace in workspaces
        }

        for row in rows:
            owner_id = getattr(row, owner_field, None)
            workspace = by_owner.get(owner_id)
            if workspace is None:
                unresolved += 1
                continue
            eligible += 1
            if dry_run:
                continue
            row.workspace_id = workspace.id
            row.created_by_user_id = (
                row.created_by_user_id or owner_id
            )

        if not dry_run:
            await db.flush()

    return {
        "checked": checked,
        "updated": 0 if dry_run else eligible,
        "would_update": eligible if dry_run else 0,
        "unresolved": unresolved,
    }


async def backfill_workspace_scope(
    db: AsyncSession,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    tables: tuple[str, ...] | None = None,
) -> dict[str, dict[str, int]]:
    """回填商品与变体；无法确定个人工作区的数据只报告，不猜测。"""

    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    selected_tables = tables or tuple(SCOPED_MODELS)
    unknown = set(selected_tables) - set(SCOPED_MODELS)
    if unknown:
        raise ValueError(f"不支持的回填表：{', '.join(sorted(unknown))}")

    return {
        table_name: await _backfill_table(
            db,
            table_name=table_name,
            batch_size=batch_size,
            dry_run=dry_run,
        )
        for table_name in selected_tables
    }


# 兼容已完成商品切片中使用的旧名称。
backfill_product_workspace_scope = backfill_workspace_scope
