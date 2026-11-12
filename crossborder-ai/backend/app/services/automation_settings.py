"""用户自动化偏好读取、更新和调度判定。"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_preference import (
    AutomationPreference,
    AutomationTaskState,
)
from app.models.user import User


PAID_PLANS = {"standard", "professional"}
TASK_FIELDS = {
    "store_check": "daily_store_check",
    "operations_monitor": "daily_operations_monitor",
    "shopify_sync": "shopify_auto_sync",
    "ab_evaluation": "ab_auto_pause",
}
FIELD_TO_TASK = {field: task for task, field in TASK_FIELDS.items()}
TASK_META = {
    "store_check": {
        "title": "整店巡检",
        "description": "每日检查商品资料、Listing、素材、SKU、发布和运营风险。",
        "schedule": "每天 02:30",
    },
    "operations_monitor": {
        "title": "运营监控",
        "description": "每日生成库存、毛利、补货和 Listing 风险快照。",
        "schedule": "每天 02:45",
    },
    "shopify_sync": {
        "title": "Shopify 自动同步",
        "description": "同步订单、销售额、销量和库存，并回写营销活动效果。",
        "schedule": "每 6 小时",
    },
    "ab_evaluation": {
        "title": "A/B 自动暂停",
        "description": "样本充足且差距明确时暂停落后版本，并标记推荐版本。",
        "schedule": "效果数据导入后",
    },
}


async def get_or_create_preferences(
    db: AsyncSession,
    user_id,
) -> AutomationPreference:
    preference = await db.get(AutomationPreference, user_id)
    if preference is None:
        preference = AutomationPreference(user_id=user_id)
        db.add(preference)
        await db.flush()
    return preference


def effective_automation_enabled(
    user: User,
    preference: AutomationPreference,
    task: str,
) -> bool:
    """套餐资格和用户开关同时满足时才执行。"""
    field = TASK_FIELDS.get(task)
    if field is None:
        return False
    return user.plan in PAID_PLANS and bool(getattr(preference, field))


async def automation_enabled_for_user(
    db: AsyncSession,
    user: User,
    task: str,
) -> bool:
    preference = await get_or_create_preferences(db, user.id)
    return effective_automation_enabled(user, preference, task)


def serialize_automation_settings(
    user: User,
    preference: AutomationPreference,
    states: list[AutomationTaskState],
) -> dict[str, Any]:
    by_task = {state.task: state for state in states}
    eligible = user.plan in PAID_PLANS
    return {
        "eligible": eligible,
        "plan": user.plan,
        "tasks": [
            {
                "key": task,
                "title": TASK_META[task]["title"],
                "description": TASK_META[task]["description"],
                "schedule": TASK_META[task]["schedule"],
                "enabled": bool(getattr(preference, field)),
                "effective_enabled": effective_automation_enabled(
                    user,
                    preference,
                    task,
                ),
                "last_run_at": (
                    by_task[task].last_run_at.isoformat()
                    if task in by_task and by_task[task].last_run_at
                    else None
                ),
                "status": by_task[task].status if task in by_task else "never",
                "error": by_task[task].error if task in by_task else None,
            }
            for task, field in TASK_FIELDS.items()
        ],
    }


async def load_automation_settings(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    preference = await get_or_create_preferences(db, user.id)
    states = (
        await db.execute(
            select(AutomationTaskState).where(
                AutomationTaskState.user_id == user.id
            )
        )
    ).scalars().all()
    return serialize_automation_settings(user, preference, list(states))


async def update_automation_settings(
    db: AsyncSession,
    user: User,
    updates: dict[str, bool],
) -> dict[str, Any]:
    """保存开关；Free 用户不能主动开启业务自动化。"""
    if user.plan not in PAID_PLANS and any(updates.values()):
        raise PermissionError("Standard 及以上套餐才能开启业务自动化")
    preference = await get_or_create_preferences(db, user.id)
    for key, value in updates.items():
        if key not in FIELD_TO_TASK:
            continue
        setattr(preference, key, bool(value))
    await db.flush()
    return await load_automation_settings(db, user)


async def record_task_state(
    db: AsyncSession,
    *,
    user_id,
    task: str,
    status: str,
    error: str | None = None,
) -> AutomationTaskState:
    """写入最近一次真实执行结果，最多保留 500 字错误摘要。"""
    state = await db.get(AutomationTaskState, (user_id, task))
    if state is None:
        state = AutomationTaskState(user_id=user_id, task=task)
        db.add(state)
    state.last_run_at = datetime.now(timezone.utc)
    state.status = status
    state.error = (error or "")[:500] or None
    await db.flush()
    return state
