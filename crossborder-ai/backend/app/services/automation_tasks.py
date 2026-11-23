"""按用户自动化偏好执行的定时业务任务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.automation_settings import (
    automation_enabled_for_user,
    record_task_state,
)
from app.services.operations_monitor import run_monitor_scan
from app.services.store_check_service import run_store_check
from app.services.workspaces import ensure_personal_workspace


async def _paid_work_scopes(
    db: AsyncSession,
    row_query,
) -> list[tuple[User, object]]:
    rows = (await db.execute(row_query)).all()
    scopes: list[tuple[User, object]] = []
    seen: set[tuple[object, object]] = set()
    for workspace_id, user_id in rows:
        user = await db.get(User, user_id)
        if user and user.plan in {"standard", "professional"}:
            resolved_workspace = (
                workspace_id
                or (await ensure_personal_workspace(db, user)).id
            )
            key = (resolved_workspace, user.id)
            if key not in seen:
                seen.add(key)
                scopes.append((user, resolved_workspace))
    return scopes


async def run_scheduled_store_checks(db: AsyncSession) -> dict:
    """执行开启自动化的用户整店巡检，并记录真实执行状态。"""
    scopes = await _paid_work_scopes(
        db,
        select(Product.workspace_id, Product.user_id).distinct(),
    )
    result = {
        "scanned": len(scopes),
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
    }
    for user, workspace_id in scopes:
        if not await automation_enabled_for_user(
            db,
            user,
            "store_check",
            workspace_id=workspace_id,
        ):
            result["skipped"] += 1
            continue
        try:
            async with db.begin_nested():
                await run_store_check(
                    db,
                    user,
                    workspace_id=workspace_id,
                )
            await record_task_state(
                db,
                user_id=user.id,
                workspace_id=workspace_id,
                task="store_check",
                status="success",
            )
            result["succeeded"] += 1
        except Exception as exc:
            await record_task_state(
                db,
                user_id=user.id,
                workspace_id=workspace_id,
                task="store_check",
                status="failed",
                error=str(exc),
            )
            result["failed"] += 1
    return result


async def run_scheduled_operations_monitors(db: AsyncSession) -> dict:
    """执行开启自动化的用户运营监控，并记录执行状态。"""
    scopes = await _paid_work_scopes(
        db,
        select(
            ProductVariant.workspace_id,
            ProductVariant.user_id,
        ).distinct(),
    )
    result = {
        "scanned": len(scopes),
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
    }
    for user, workspace_id in scopes:
        if not await automation_enabled_for_user(
            db,
            user,
            "operations_monitor",
            workspace_id=workspace_id,
        ):
            result["skipped"] += 1
            continue
        try:
            async with db.begin_nested():
                await run_monitor_scan(
                    db,
                    user,
                    workspace_id=workspace_id,
                )
            await record_task_state(
                db,
                user_id=user.id,
                workspace_id=workspace_id,
                task="operations_monitor",
                status="success",
            )
            result["succeeded"] += 1
        except Exception as exc:
            await record_task_state(
                db,
                user_id=user.id,
                workspace_id=workspace_id,
                task="operations_monitor",
                status="failed",
                error=str(exc),
            )
            result["failed"] += 1
    return result
