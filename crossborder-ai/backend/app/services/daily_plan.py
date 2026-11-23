"""按工作区业务日期组织可执行的每日计划与日结。"""

import json
from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_work import WorkItem
from app.models.daily_plan import AgentDay, DailyPlanItem
from app.models.workspace import Workspace
from app.services.notifications import create_notification
from app.services.business_time import business_day_utc_bounds


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _priority_score(item: WorkItem) -> int:
    base = {"urgent": 100, "attention": 60}.get(item.priority, 20)
    due_at = _as_utc(item.due_at)
    if due_at is not None:
        remaining = due_at - datetime.now(timezone.utc)
        if remaining.total_seconds() < 4 * 3600:
            base += 30
    return base


def _category(item: WorkItem, day_start: datetime) -> str:
    created_at = _as_utc(item.created_at)
    if created_at is not None and created_at < day_start:
        return "carryover"
    if item.status == "running":
        return "auto"
    if item.status == "waiting_user" and item.requires_action != "none":
        return "decision"
    return "monitor"


def _expected_action(item: WorkItem, category: str) -> str:
    if category == "decision":
        return "等待你确认后由 Agent 执行"
    if category == "auto":
        return "Agent 正在自动处理"
    if category == "carryover":
        return "继续处理昨天未完成的工作"
    return "Agent 持续观察，有变化时再提醒"


async def get_agent_day(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    business_date: date,
) -> AgentDay | None:
    return (
        await db.execute(
            select(AgentDay).where(
                AgentDay.workspace_id == workspace_id,
                AgentDay.business_date == business_date,
            )
        )
    ).scalar_one_or_none()


async def get_daily_plan(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    business_date: date,
) -> list[DailyPlanItem]:
    day = await get_agent_day(
        db,
        workspace_id=workspace_id,
        business_date=business_date,
    )
    if day is None:
        return []
    return (
        await db.execute(
            select(DailyPlanItem)
            .where(
                DailyPlanItem.workspace_id == workspace_id,
                DailyPlanItem.agent_day_id == day.id,
            )
            .order_by(
                DailyPlanItem.priority_score.desc(),
                DailyPlanItem.created_at,
            )
        )
    ).scalars().all()


async def build_daily_plan(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    business_date: date,
    timezone_name: str = "Asia/Shanghai",
) -> AgentDay:
    """读取真实开放工作项，生成不重复、可追溯到工作项的晨报。"""

    existing = await get_agent_day(
        db,
        workspace_id=workspace_id,
        business_date=business_date,
    )
    if existing is not None:
        return existing

    day_start, day_end = business_day_utc_bounds(
        business_date,
        timezone_name,
    )
    items = (
        await db.execute(
            select(WorkItem)
            .where(
                WorkItem.workspace_id == workspace_id,
                WorkItem.status.in_(
                    ["waiting_user", "running", "blocked", "failed"]
                ),
            )
            .order_by(WorkItem.created_at, WorkItem.id)
        )
    ).scalars().all()
    current_or_carryover = [
        item
        for item in items
        if _as_utc(item.created_at) is None
        or _as_utc(item.created_at) < day_end
    ]
    day = AgentDay(
        workspace_id=workspace_id,
        business_date=business_date,
        timezone=timezone_name,
        status="active",
        plan_version=1,
        morning_brief_at=datetime.now(timezone.utc),
    )
    db.add(day)
    await db.flush()

    plan_items: list[DailyPlanItem] = []
    for item in current_or_carryover:
        category = _category(item, day_start)
        plan_item = DailyPlanItem(
            workspace_id=workspace_id,
            agent_day_id=day.id,
            work_item_id=item.id,
            category=category,
            priority_score=_priority_score(item),
            planned_at=datetime.now(timezone.utc),
            reason=item.summary,
            expected_action=_expected_action(item, category),
            status="planned",
        )
        db.add(plan_item)
        plan_items.append(plan_item)

    decisions = sorted(
        [item for item in plan_items if item.category == "decision"],
        key=lambda item: item.priority_score,
        reverse=True,
    )
    automatic = [item for item in plan_items if item.category == "auto"]
    monitors = [item for item in plan_items if item.category == "monitor"]
    brief = {
        "overview": (
            f"今天有 {len(decisions)} 件需要你决定"
            if decisions
            else "今天没有需要你立即决定的事"
        ),
        "decision_count": len(decisions),
        "auto_count": len(automatic),
        "monitor_count": len(monitors),
        "top_decision": (
            {
                "work_item_id": str(decisions[0].work_item_id),
                "reason": decisions[0].reason,
            }
            if decisions
            else None
        ),
        "auto_items": [
            {
                "work_item_id": str(item.work_item_id),
                "reason": item.reason,
            }
            for item in automatic[:3]
        ],
        "monitor_items": [
            {
                "work_item_id": str(item.work_item_id),
                "reason": item.reason,
            }
            for item in monitors[:3]
        ],
    }
    day.morning_brief_json = _json(brief)
    workspace = await db.get(Workspace, workspace_id)
    if workspace is not None:
        await create_notification(
            db,
            workspace_id=workspace_id,
            user_id=workspace.owner_user_id,
            notification_type="morning_brief",
            title="今日计划已生成",
            body=brief["overview"],
            deep_link=f"/plan?workspaceId={workspace_id}",
            dedupe_key=f"agent-day:{day.id}:morning-brief",
        )
    await db.flush()
    return day


async def close_daily_plan(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    business_date: date,
) -> AgentDay:
    """按工作项真实状态生成日结，失败和延续不会被隐藏。"""

    day = await get_agent_day(
        db,
        workspace_id=workspace_id,
        business_date=business_date,
    )
    if day is None:
        raise ValueError("当天计划不存在")
    plan_items = await get_daily_plan(
        db,
        workspace_id=workspace_id,
        business_date=business_date,
    )
    work_ids = [item.work_item_id for item in plan_items]
    work_items = (
        await db.execute(
            select(WorkItem).where(WorkItem.id.in_(work_ids))
        )
    ).scalars().all() if work_ids else []
    by_id = {item.id: item for item in work_items}
    summary = {
        "planned": len(plan_items),
        "completed": 0,
        "failed": 0,
        "waiting": 0,
        "carryover": 0,
        "unfinished": [],
    }
    for plan_item in plan_items:
        work_item = by_id.get(plan_item.work_item_id)
        if work_item is None:
            continue
        if plan_item.category == "carryover":
            summary["carryover"] += 1
        if work_item.status == "succeeded":
            summary["completed"] += 1
            plan_item.status = "completed"
        elif work_item.status in {"failed", "blocked"}:
            summary["failed"] += 1
            summary["unfinished"].append(
                {"work_item_id": str(work_item.id), "title": work_item.title}
            )
        else:
            summary["waiting"] += 1
            summary["unfinished"].append(
                {"work_item_id": str(work_item.id), "title": work_item.title}
            )
    day.status = "closed"
    day.closeout_at = datetime.now(timezone.utc)
    day.closeout_json = _json(summary)
    workspace = await db.get(Workspace, workspace_id)
    if workspace is not None:
        await create_notification(
            db,
            workspace_id=workspace_id,
            user_id=workspace.owner_user_id,
            notification_type="day_closeout",
            title="今日日结已生成",
            body="查看今天完成、等待和明日延续的工作。",
            deep_link=f"/plan?workspaceId={workspace_id}",
            dedupe_key=f"agent-day:{day.id}:closeout",
        )
    await db.flush()
    return day


async def run_scheduled_daily_plans(db: AsyncSession) -> dict:
    """每小时检查各工作区本地时间，08:00 建计划、20:00 做日结。"""

    workspaces = (
        await db.execute(
            select(Workspace).where(Workspace.status == "active")
        )
    ).scalars().all()
    result = {"workspaces_checked": len(workspaces), "plans": 0, "closed": 0}
    for workspace in workspaces:
        try:
            settings = json.loads(workspace.settings_json or "{}")
        except json.JSONDecodeError:
            settings = {}
        timezone_name = str(
            settings.get("timezone") or "Asia/Shanghai"
        )
        try:
            local_now = datetime.now(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            timezone_name = "UTC"
            local_now = datetime.now(timezone.utc)
        business_date = local_now.date()
        if local_now.hour == 8:
            await build_daily_plan(
                db,
                workspace_id=workspace.id,
                business_date=business_date,
                timezone_name=timezone_name,
            )
            await db.commit()
            result["plans"] += 1
        elif local_now.hour == 20:
            day = await get_agent_day(
                db,
                workspace_id=workspace.id,
                business_date=business_date,
            )
            if day is not None and day.status != "closed":
                await close_daily_plan(
                    db,
                    workspace_id=workspace.id,
                    business_date=business_date,
                )
                await db.commit()
                result["closed"] += 1
    return result
