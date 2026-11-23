"""每日计划与日结核心行为测试。"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.agent_work import WorkItem
from app.models.user import User
from app.services.daily_plan import (
    build_daily_plan,
    close_daily_plan,
    get_daily_plan,
)
from app.services.business_time import business_day_utc_bounds
from app.services.work_items import create_work_item
from app.services.workspaces import ensure_personal_workspace


async def _workspace_with_items(db_session):
    user = User(
        email="daily-plan@example.com",
        username="daily-plan",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    decision = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="order_exception",
        source="integration",
        title="订单将在四小时后超时",
        summary="供应商尚未揽收。",
        priority="urgent",
        requires_action="confirm",
        due_at=datetime.now(timezone.utc) + timedelta(hours=4),
    )
    automatic = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="inventory_sync",
        source="agent",
        title="同步库存",
        summary="Agent 正在同步库存。",
        status="running",
        requires_action="none",
        current_step="同步中",
    )
    previous = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="customer_reply",
        source="integration",
        title="昨天未回复的客户消息",
        summary="需要今天继续处理。",
        requires_action="confirm",
    )
    previous.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    return user, workspace, decision, automatic, previous


@pytest.mark.asyncio
async def test_daily_plan_classifies_actionable_items_without_duplicates(
    db_session,
):
    _user, workspace, _decision, _automatic, _previous = (
        await _workspace_with_items(db_session)
    )
    business_date = datetime.now(timezone.utc).date()

    first = await build_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=business_date,
        timezone_name="Asia/Shanghai",
    )
    second = await build_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=business_date,
        timezone_name="Asia/Shanghai",
    )
    await db_session.commit()

    assert first.id == second.id
    assert first.plan_version == 1
    assert second.plan_version == 1
    items = await get_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=business_date,
    )
    assert len(items) == 3
    categories = {item.category for item in items}
    assert {"decision", "auto", "carryover"} <= categories
    assert "最多只展示一个" not in (first.morning_brief_json or "")


@pytest.mark.asyncio
async def test_daily_plan_uses_local_midnight_before_utc_day(db_session):
    user = User(
        email="daily-plan-local-date@example.com",
        username="daily-plan-local-date",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="order_exception",
        source="integration",
        title="上海凌晨订单",
        summary="不能被误判为昨日延续。",
        requires_action="confirm",
    )
    local_start, _ = business_day_utc_bounds(
        date(2026, 11, 22),
        "Asia/Shanghai",
    )
    item.created_at = local_start.replace(minute=30)
    await db_session.commit()

    await build_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=date(2026, 11, 22),
        timezone_name="Asia/Shanghai",
    )
    await db_session.commit()
    items = await get_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=date(2026, 11, 22),
    )

    assert [(entry.work_item_id, entry.category) for entry in items] == [
        (item.id, "decision")
    ]


@pytest.mark.asyncio
async def test_day_closeout_distinguishes_completed_waiting_and_carryover(
    db_session,
):
    _user, workspace, decision, automatic, previous = (
        await _workspace_with_items(db_session)
    )
    business_date = datetime.now(timezone.utc).date()
    await build_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=business_date,
        timezone_name="Asia/Shanghai",
    )
    decision.status = "succeeded"
    automatic.status = "blocked"
    previous.status = "waiting_user"
    await db_session.commit()

    closed = await close_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=business_date,
    )
    await db_session.commit()

    assert closed.status == "closed"
    assert closed.closeout_json is not None
    assert "completed" in closed.closeout_json
    assert "failed" in closed.closeout_json
    assert "carryover" in closed.closeout_json
    plan_items = await get_daily_plan(
        db_session,
        workspace_id=workspace.id,
        business_date=business_date,
    )
    assert any(item.work_item_id == decision.id for item in plan_items)
    assert any(item.work_item_id == automatic.id for item in plan_items)
    assert any(item.work_item_id == previous.id for item in plan_items)
