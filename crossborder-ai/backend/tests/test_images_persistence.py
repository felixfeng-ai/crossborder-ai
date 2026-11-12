"""VeyaShip - 图片生成任务落库（CAP-07）测试

覆盖行为契约：
1. POST /images/generate 落 pending 记录并返回 task_id（可查询）
2. 生成执行后状态写回 DB：completed + image_urls
3. GET /images/status/{task_id} 从库读（不存在 404 中文）
4. GET /images/history 返回当前用户最近 N 条、按时间倒序、跨用户隔离
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.routers import images as images_router
from app.services.ai.aliyun_image import AliyunImageService


async def _current_user_id(db_session) -> uuid.UUID:
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    user = result.scalar_one()
    return user.id


async def _set_professional_plan(db_session) -> None:
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    user = result.scalar_one()
    user.plan = "professional"
    await db_session.flush()


# ── 1. 提交即落库（pending） ─────────────────────────────────

@pytest.mark.asyncio
async def test_generate_persists_pending_row(
    client: AsyncClient, auth_headers: dict, db_session, monkeypatch
):
    """POST /images/generate → 返回 task_id 且 image_generation_tasks 有对应 pending 记录"""
    await _set_professional_plan(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-aliyun-key")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")

    # 避免后台任务访问文件 DB：替换为 no-op
    async def _noop(*args, **kwargs):
        return None
    monkeypatch.setattr(images_router, "_execute_image_task", _noop)

    resp = await client.post(
        "/api/v1/images/generate",
        json={"prompt": "a red sneaker on white background", "num_outputs": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    task_id = uuid.UUID(data["task_id"])

    result = await db_session.execute(
        select(ImageGenerationTask).where(ImageGenerationTask.id == task_id)
    )
    row = result.scalar_one()
    assert row.user_id == await _current_user_id(db_session)
    assert row.status == "pending"
    assert row.credits_cost == 3
    assert "red sneaker" in row.prompt


# ── 2. 执行后状态写回 DB ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_writes_completed_status(
    client: AsyncClient, auth_headers: dict, db_session, monkeypatch
):
    """_run_generation 执行成功 → DB 记录 completed + image_urls，/status 可读到"""
    await _set_professional_plan(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-aliyun-key")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")

    # 造一个 pending 记录
    uid = await _current_user_id(db_session)
    task = ImageGenerationTask(user_id=uid, prompt="pink chair", status="pending", image_urls="[]")
    db_session.add(task)
    await db_session.flush()
    task_id = str(task.id)

    # mock 图片服务返回 URL
    async def fake_generate_image(self, prompt: str, num_outputs: int = 1, size: str = "1024*1024"):
        return ["https://img.example.com/out/1.png"]

    monkeypatch.setattr(AliyunImageService, "generate_image", fake_generate_image)

    await images_router._run_generation(task_id, "pink chair", 1, db=db_session)

    # DB 已写回
    result = await db_session.execute(
        select(ImageGenerationTask).where(ImageGenerationTask.id == uuid.UUID(task_id))
    )
    row = result.scalar_one()
    assert row.status == "completed"
    urls = json.loads(row.image_urls)
    assert urls == ["https://img.example.com/out/1.png"]

    # /status 从库读到同样结果
    resp = await client.get(f"/api/v1/images/status/{task_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["image_urls"] == ["https://img.example.com/out/1.png"]


# ── 3. /status 不存在 → 404 中文 ─────────────────────────────

@pytest.mark.asyncio
async def test_status_missing_returns_404_chinese(client: AsyncClient, auth_headers: dict):
    """查询不存在的 task_id → 404 中文提示"""
    missing = uuid.uuid4()
    resp = await client.get(f"/api/v1/images/status/{missing}", headers=auth_headers)
    assert resp.status_code == 404
    assert "任务不存在" in resp.json()["detail"]


# ── 4. /history 当前用户 + 时间倒序 + 隔离 ────────────────────

@pytest.mark.asyncio
async def test_history_returns_own_recent_only(
    client: AsyncClient, auth_headers: dict, db_session
):
    """history 只返回当前用户记录、按 created_at 倒序；不含其他用户的任务"""
    uid = await _current_user_id(db_session)
    other_uid = uuid.uuid4()
    base = datetime.now(timezone.utc)

    def _task(user_id, prompt, offset_min, status="completed", urls=None):
        return ImageGenerationTask(
            user_id=user_id,
            prompt=prompt,
            status=status,
            image_urls=json.dumps(urls or [f"https://img.example.com/{prompt}.png"]),
            model_used="wanx",
            created_at=base - timedelta(minutes=offset_min),
        )

    db_session.add_all([
        _task(uid, "older", 30),
        _task(uid, "newer", 5),
        _task(uid, "middle", 15),
        _task(other_uid, "other-user", 1),   # 别人的任务，不应返回
    ])
    await db_session.flush()

    resp = await client.get("/api/v1/images/history", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    prompts = [i["prompt"] for i in items]
    # 时间倒序：newer → middle → older
    assert prompts == ["newer", "middle", "older"]
    assert "other-user" not in prompts
    assert all(i["status"] == "completed" for i in items)
    assert items[0]["image_urls"] == ["https://img.example.com/newer.png"]
    assert items[0]["task_id"]


@pytest.mark.asyncio
async def test_history_respects_limit(
    client: AsyncClient, auth_headers: dict, db_session
):
    """history 支持 limit 参数，默认 20 条上限内的自定义值生效"""
    uid = await _current_user_id(db_session)
    base = datetime.now(timezone.utc)
    db_session.add_all([
        ImageGenerationTask(
            user_id=uid,
            prompt=f"task-{i}",
            status="completed",
            image_urls="[]",
            created_at=base - timedelta(minutes=i),
        )
        for i in range(5)
    ])
    await db_session.flush()

    resp = await client.get("/api/v1/images/history", params={"limit": 2}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    # 最新在前
    assert items[0]["prompt"] == "task-0"
    assert items[1]["prompt"] == "task-1"
