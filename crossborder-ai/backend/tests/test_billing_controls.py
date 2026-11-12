"""高成本入口计费与失败退款测试。"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import app.routers.radar as radar_router
import app.routers.shopify as shopify_router
import app.services.video_task_executor as video_executor
from app.models.credit_transaction import CreditTransaction
from app.models.feature_usage import FeatureUsageCounter
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask


async def _register_with_credits(client, db_session, *, credits: int = 5):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"billing-{uuid.uuid4().hex[:8]}@example.com",
            "username": "billing-user",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    user = (
        await db_session.execute(
            select(User).where(User.email == response.json().get("email", ""))
        )
    ).scalar_one_or_none()
    if user is None:
        user = (
            await db_session.execute(select(User).order_by(User.created_at.desc()))
        ).scalars().first()
    user.credits = credits
    await db_session.flush()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, user


@pytest.mark.asyncio
async def test_shopify_compliance_requires_login_and_charges_one_credit(
    client,
    db_session,
    monkeypatch,
):
    anonymous = await client.post(
        "/api/v1/shopify/compliance",
        json={"text": "普通商品描述"},
    )
    assert anonymous.status_code == 401

    headers, user = await _register_with_credits(client, db_session, credits=5)

    async def safe_check(text):
        return {"safe": True, "reason": None}

    monkeypatch.setattr(shopify_router, "ai_compliance_check", safe_check)
    response = await client.post(
        "/api/v1/shopify/compliance",
        json={"text": "普通商品描述"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    assert user.credits == 4
    ledger = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.feature == "shopify_compliance",
            )
        )
    ).scalar_one()
    assert ledger.delta == -1


@pytest.mark.asyncio
async def test_radar_scrape_charges_only_after_success(client, db_session, monkeypatch):
    headers, user = await _register_with_credits(client, db_session, credits=5)
    db_session.add(
        FeatureUsageCounter(
            user_id=user.id,
            feature="radar_scrape",
            period_key=datetime.now(timezone.utc).strftime("%Y-%m"),
            used=10,
        )
    )
    await db_session.flush()

    async def fake_refresh(db):
        return None

    async def fake_scrape(url, **kwargs):
        return {"title": "competitor", "price": 12.5}

    monkeypatch.setattr(radar_router.provider_config, "refresh", fake_refresh)
    monkeypatch.setattr(
        radar_router.provider_config,
        "get",
        lambda group, key, default="": default,
    )
    monkeypatch.setattr(radar_router, "scrape_1688", fake_scrape)

    response = await client.get(
        "/api/v1/radar/scrape",
        params={"url": "https://detail.1688.com/offer/123456789.html"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    assert user.credits == 3
    ledger = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.feature == "radar_scrape_overage",
            )
        )
    ).scalar_one()
    assert ledger.delta == -2


@pytest.mark.asyncio
async def test_failed_video_task_refunds_charged_credits_once(
    db_session,
    monkeypatch,
):
    user = User(
        id=uuid.uuid4(),
        email=f"video-refund-{uuid.uuid4().hex[:8]}@example.com",
        username="video-refund",
        password_hash="x",
        plan="professional",
        credits=90,
    )
    db_session.add(user)
    await db_session.flush()
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="failed video",
        provider_task_id="provider-failed",
        status="running",
        credits_cost=10,
        credits_charged=10,
    )
    db_session.add(task)
    await db_session.flush()

    async def fake_query(provider_task_id):
        return {"status": "failed", "error": "审核失败"}

    monkeypatch.setattr(
        "app.services.video_provider.query_minimax_video",
        fake_query,
    )
    await video_executor._poll_one(db_session, task)
    await video_executor._refund_video_task(db_session, task)
    await db_session.commit()

    await db_session.refresh(user)
    await db_session.refresh(task)
    assert user.credits == 100
    assert task.status == "failed"
    assert task.credits_refunded == 10
    ledger = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.feature == "ai_video_refund",
            )
        )
    ).scalar_one()
    assert ledger.delta == 10
