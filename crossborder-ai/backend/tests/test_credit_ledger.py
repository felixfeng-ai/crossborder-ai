"""积分流水与月度额度测试。"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.credit_transaction import CreditTransaction
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services.ai.aliyun_image import AliyunImageService
from app.services.image_task_executor import run_image_generation
from app.services.credit_service import apply_monthly_allowance
import app.services.image_task_executor as image_executor


async def _create_user(db_session, *, credits: int = 10, plan: str = "free") -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"credit-{uuid.uuid4().hex[:8]}@example.com",
        username="credit-user",
        password_hash="x",
        credits=credits,
        plan=plan,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_deduct_credits_writes_auditable_ledger(db_session):
    user = await _create_user(db_session, credits=10)

    remaining = await user.deduct_credits(
        db_session,
        3,
        feature="ai_listing",
        reference_type="listing",
        reference_id="listing-1",
        description="生成 Listing",
    )

    assert remaining == 7
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        )
    ).scalar_one()
    assert transaction.delta == -3
    assert transaction.balance_after == 7
    assert transaction.feature == "ai_listing"
    assert transaction.reference_id == "listing-1"


@pytest.mark.asyncio
async def test_monthly_allowance_resets_once_per_month(db_session):
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    user = await _create_user(db_session, credits=4, plan="free")
    user.credit_period_start = now - timedelta(days=40)
    await db_session.flush()

    transaction = await apply_monthly_allowance(db_session, user, now=now)
    repeated = await apply_monthly_allowance(db_session, user, now=now)

    assert transaction is not None
    assert repeated is None
    assert user.credits == 30
    assert user.credit_period_start == now
    assert transaction.delta == 26
    assert transaction.balance_after == 30
    assert transaction.feature == "monthly_allowance"

    count = (
        await db_session.execute(
            select(func.count()).select_from(CreditTransaction)
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_registration_creates_free_monthly_grant(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"grant-{uuid.uuid4().hex[:8]}@example.com",
            "username": "grant-user",
            "password": "testpass123",
        },
    )

    assert response.status_code == 201, response.text
    user = (
        await db_session.execute(select(User).order_by(User.created_at.desc()))
    ).scalars().first()
    assert user.credits == 30
    assert user.credit_period_start is not None
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        )
    ).scalar_one()
    assert transaction.delta == 30
    assert transaction.feature == "monthly_allowance"


@pytest.mark.asyncio
async def test_image_generation_charges_once_per_output(db_session, monkeypatch):
    user = await _create_user(db_session, credits=5, plan="professional")
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="white sneaker",
        num_outputs=2,
        status="processing",
        image_urls="[]",
        credits_cost=2,
    )
    db_session.add(task)
    await db_session.flush()

    monkeypatch.setattr(
        image_executor.provider_config,
        "get",
        lambda group, key, default="": (
            "test-key" if group == "aliyun" and key == "api_key" else default
        ),
    )

    async def fake_generate_image(self, prompt, num_outputs=1, size="1024*1024"):
        return ["https://img.example.com/a.png", "https://img.example.com/b.png"]

    monkeypatch.setattr(AliyunImageService, "generate_image", fake_generate_image)

    await run_image_generation(db_session, task.id, task.prompt, task.num_outputs)
    await run_image_generation(db_session, task.id, task.prompt, task.num_outputs)

    await db_session.refresh(user)
    await db_session.refresh(task)
    assert user.credits == 3
    assert task.credits_charged == 2
    transactions = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.feature == "ai_image",
            )
        )
    ).scalars().all()
    assert len(transactions) == 1
    assert transactions[0].delta == -2


@pytest.mark.asyncio
async def test_failed_image_generation_does_not_charge(db_session, monkeypatch):
    user = await _create_user(db_session, credits=5, plan="professional")
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="white sneaker",
        num_outputs=1,
        status="processing",
        image_urls="[]",
        credits_cost=1,
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(
        image_executor.provider_config,
        "get",
        lambda group, key, default="": default,
    )

    await run_image_generation(db_session, task.id, task.prompt, task.num_outputs)

    await db_session.refresh(user)
    await db_session.refresh(task)
    assert user.credits == 5
    assert task.status == "failed"
    assert task.credits_charged == 0


@pytest.mark.asyncio
async def test_free_user_cannot_run_agent_workflow(client):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"free-workflow-{uuid.uuid4().hex[:8]}@example.com",
            "username": "free-workflow",
            "password": "testpass123",
        },
    )
    assert registered.status_code == 201, registered.text

    response = await client.post(
        "/api/v1/agent/workflow",
        json={"workflow": "store_check"},
        headers={
            "Authorization": f"Bearer {registered.json()['access_token']}",
            "Idempotency-Key": f"free-workflow-{uuid.uuid4().hex}",
        },
    )

    assert response.status_code == 403
