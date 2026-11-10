"""Durable image generation queue behavior."""

import inspect
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.routers import images as images_router
from app.services import scheduler as scheduler_module


def _make_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _make_professional(db_session) -> None:
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.plan = "professional"
    await db_session.flush()


@pytest.mark.asyncio
async def test_image_submit_persists_pending_queue_task(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    await _make_professional(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")

    assert "create_task" not in inspect.getsource(images_router.schedule_image_task)

    response = await client.post(
        "/api/v1/images/generate",
        json={"prompt": "a durable queue product photo", "num_outputs": 2},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    task = (
        await db_session.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.id == uuid.UUID(response.json()["task_id"])
            )
        )
    ).scalar_one()
    assert task.status == "pending"
    assert task.num_outputs == 2
    assert task.attempts == 0


@pytest.mark.asyncio
async def test_scheduler_claims_and_recovers_image_tasks(monkeypatch):
    engine, factory = _make_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(scheduler_module, "async_session_factory", factory)

    async with factory() as db:
        user = User(email="image-queue@test.com", username="image-queue", password_hash="x")
        db.add(user)
        await db.flush()
        pending = ImageGenerationTask(
            user_id=user.id,
            prompt="pending task",
            status="pending",
            image_urls="[]",
            num_outputs=1,
        )
        stale = ImageGenerationTask(
            user_id=user.id,
            prompt="stale task",
            status="processing",
            image_urls="[]",
            num_outputs=1,
            attempts=1,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=11),
        )
        db.add_all([pending, stale])
        await db.commit()
        pending_id = pending.id
        stale_id = stale.id

    claimed = await scheduler_module.SchedulerService()._claim_image_tasks()

    async with factory() as db:
        pending_now = (
            await db.execute(
                select(ImageGenerationTask).where(ImageGenerationTask.id == pending_id)
            )
        ).scalar_one()
        stale_now = (
            await db.execute(
                select(ImageGenerationTask).where(ImageGenerationTask.id == stale_id)
            )
        ).scalar_one()
        assert [task.id for task in claimed] == [pending_id]
        assert pending_now.status == "processing"
        assert pending_now.attempts == 1
        assert pending_now.started_at is not None
        assert stale_now.status == "pending"
        assert stale_now.started_at is None
