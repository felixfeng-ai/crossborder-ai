"""协作工作项与命令行为测试。"""

import pytest
from uuid import uuid4

from app.models.agent_task import AgentTask
from app.models.user import User
from app.services.work_items import (
    complete_work_item_from_agent_task,
    create_work_item,
    get_work_item,
    submit_work_item_command,
)
from app.services.workspaces import ensure_personal_workspace


async def _user_and_workspace(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    await db_session.commit()
    return user, workspace


@pytest.mark.asyncio
async def test_work_item_command_is_versioned_and_idempotent(db_session):
    owner, workspace = await _user_and_workspace(db_session, "work-item@example.com")

    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=owner.id,
        kind="order_exception",
        source="integration",
        title="两个订单四小时后超时",
        summary="供应商尚未揽收。",
        priority="urgent",
        requires_action="confirm",
        source_type="shopify_order",
        source_id="order-1001",
    )
    await db_session.commit()

    assert item.status == "waiting_user"
    assert item.version == 1

    first = await submit_work_item_command(
        db_session,
        workspace_id=workspace.id,
        work_item_id=item.id,
        actor_user_id=owner.id,
        action="confirm",
        expected_version=1,
        payload={"option": "delay_notice"},
        idempotency_key="gesture-1",
    )
    await db_session.commit()
    await db_session.refresh(item)

    assert first.status == "accepted"
    assert item.status == "running"
    assert item.version == 2

    second = await submit_work_item_command(
        db_session,
        workspace_id=workspace.id,
        work_item_id=item.id,
        actor_user_id=owner.id,
        action="confirm",
        expected_version=1,
        payload={"option": "delay_notice"},
        idempotency_key="gesture-1",
    )
    await db_session.commit()
    await db_session.refresh(item)

    assert second.id == first.id
    assert item.status == "running"
    assert item.version == 2


@pytest.mark.asyncio
async def test_work_item_is_workspace_scoped(db_session):
    first_user, first_workspace = await _user_and_workspace(
        db_session,
        "work-item-a@example.com",
    )
    _second_user, second_workspace = await _user_and_workspace(
        db_session,
        "work-item-b@example.com",
    )

    item = await create_work_item(
        db_session,
        workspace_id=first_workspace.id,
        actor_user_id=first_user.id,
        kind="listing_action",
        source="agent",
        title="新品等待发布",
        summary="Listing 已准备。",
        priority="attention",
        requires_action="confirm",
    )
    await db_session.commit()

    visible = await get_work_item(
        db_session,
        workspace_id=first_workspace.id,
        work_item_id=item.id,
    )
    hidden = await get_work_item(
        db_session,
        workspace_id=second_workspace.id,
        work_item_id=item.id,
    )

    assert visible is not None
    assert hidden is None


@pytest.mark.asyncio
async def test_agent_task_result_updates_linked_work_item(db_session):
    owner, workspace = await _user_and_workspace(
        db_session,
        "work-item-agent-task@example.com",
    )
    task_id = uuid4()
    task = AgentTask(
        id=task_id,
        user_id=owner.id,
        task_type="agent_run",
        status="succeeded",
        input="{}",
        result='{"summary":"已处理 2 个订单","steps":[]}',
        idempotency_key="agent-result-1",
        cost=1,
    )
    db_session.add(task)
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=owner.id,
        kind="agent_request",
        source="agent",
        title="处理订单",
        summary="Agent 正在处理",
        requires_action="none",
        status="running",
        source_type="agent_task",
        source_id=str(task_id),
    )
    await db_session.commit()
    initial_version = item.version

    updated = await complete_work_item_from_agent_task(
        db_session,
        agent_task_id=task_id,
        status="succeeded",
        summary="已处理 2 个订单",
        error=None,
    )
    await db_session.commit()

    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.current_step == "已完成"
    assert updated.requires_action == "none"
    assert updated.version == initial_version + 1
