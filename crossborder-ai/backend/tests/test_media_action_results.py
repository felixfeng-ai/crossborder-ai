"""媒体任务完成后的 ActionRun 与工作项回写测试。"""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.action_run import ActionRun
from app.models.agent_work import WorkItem
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services.media_action_results import sync_media_action_results
from app.services.workspaces import ensure_personal_workspace


async def _context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    task_id = uuid4()
    media_task = ImageGenerationTask(
        id=task_id,
        user_id=user.id,
        prompt="white background product",
        num_outputs=1,
        credits_cost=8,
        status="processing",
    )
    item = WorkItem(
        workspace_id=workspace.id,
        kind="agent_action",
        source="agent",
        title="确认生成商品图片",
        summary="等待生成",
        status="running",
        requires_action="none",
        current_step="媒体任务生成中",
    )
    db_session.add_all([media_task, item])
    await db_session.flush()
    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=item.id,
        action_id="media.generate_image",
        platform="internal",
        target_type="media_task",
        target_id=str(task_id),
        input_json="{}",
        status="verifying",
        risk_level="medium",
        autonomy_level="confirm",
        idempotency_key=f"media:{task_id}",
        external_id=str(task_id),
    )
    db_session.add(run)
    await db_session.commit()
    return workspace, run, item, media_task


@pytest.mark.asyncio
async def test_completed_image_task_updates_action_and_work_item(db_session):
    _workspace, run, item, task = await _context(
        db_session,
        "media-result-success@example.com",
    )
    task.status = "completed"
    task.image_urls = json.dumps(["/api/v1/images/assets/1/file"])
    await db_session.commit()

    result = await sync_media_action_results(db_session)
    await db_session.commit()
    await db_session.refresh(run)
    await db_session.refresh(item)

    assert result["completed"] == 1
    assert run.status == "succeeded"
    assert item.status == "succeeded"
    assert item.current_step == "媒体已生成"


@pytest.mark.asyncio
async def test_failed_image_task_returns_action_to_user_retry(db_session):
    _workspace, run, item, task = await _context(
        db_session,
        "media-result-failed@example.com",
    )
    task.status = "failed"
    task.error = "provider failed"
    await db_session.commit()

    result = await sync_media_action_results(db_session)
    await db_session.commit()
    await db_session.refresh(run)
    await db_session.refresh(item)

    assert result["failed"] == 1
    assert run.status == "retryable_failed"
    assert item.status == "waiting_user"
    assert item.requires_action == "retry"
