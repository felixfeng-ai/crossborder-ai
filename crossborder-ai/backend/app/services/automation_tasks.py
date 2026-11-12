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


async def _paid_users_with_rows(
    db: AsyncSession,
    row_query,
) -> list[User]:
    user_ids = (await db.execute(row_query)).scalars().all()
    users = []
    for user_id in user_ids:
        user = await db.get(User, user_id)
        if user and user.plan in {"standard", "professional"}:
            users.append(user)
    return users


async def run_scheduled_store_checks(db: AsyncSession) -> dict:
    """执行开启自动化的用户整店巡检，并记录真实执行状态。"""
    users = await _paid_users_with_rows(
        db,
        select(Product.user_id).distinct(),
    )
    result = {"scanned": len(users), "succeeded": 0, "failed": 0, "skipped": 0}
    for user in users:
        if not await automation_enabled_for_user(db, user, "store_check"):
            result["skipped"] += 1
            continue
        try:
            async with db.begin_nested():
                await run_store_check(db, user)
            await record_task_state(
                db,
                user_id=user.id,
                task="store_check",
                status="success",
            )
            result["succeeded"] += 1
        except Exception as exc:
            await record_task_state(
                db,
                user_id=user.id,
                task="store_check",
                status="failed",
                error=str(exc),
            )
            result["failed"] += 1
    return result


async def run_scheduled_operations_monitors(db: AsyncSession) -> dict:
    """执行开启自动化的用户运营监控，并记录执行状态。"""
    users = await _paid_users_with_rows(
        db,
        select(ProductVariant.user_id).distinct(),
    )
    result = {"scanned": len(users), "succeeded": 0, "failed": 0, "skipped": 0}
    for user in users:
        if not await automation_enabled_for_user(
            db,
            user,
            "operations_monitor",
        ):
            result["skipped"] += 1
            continue
        try:
            async with db.begin_nested():
                await run_monitor_scan(db, user)
            await record_task_state(
                db,
                user_id=user.id,
                task="operations_monitor",
                status="success",
            )
            result["succeeded"] += 1
        except Exception as exc:
            await record_task_state(
                db,
                user_id=user.id,
                task="operations_monitor",
                status="failed",
                error=str(exc),
            )
            result["failed"] += 1
    return result
