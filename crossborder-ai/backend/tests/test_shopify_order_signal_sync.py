"""Shopify 订单增量同步到 Agent 信号测试。"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_signal import AgentSignal, IntegrationCursor
from app.models.agent_work import WorkItem
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.shopify_order_signal_sync import (
    ShopifyRateLimitError,
    sync_shopify_order_signals,
)
from app.services.workspaces import ensure_personal_workspace


def _order(
    order_id: int,
    *,
    fulfillment_status: str | None = None,
    cancelled_at: str | None = None,
    age_hours: int = 30,
):
    now = datetime.now(timezone.utc)
    return {
        "id": order_id,
        "name": f"#{order_id}",
        "created_at": (now - timedelta(hours=age_hours)).isoformat(),
        "updated_at": now.isoformat(),
        "fulfillment_status": fulfillment_status,
        "financial_status": "paid",
        "cancelled_at": cancelled_at,
    }


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
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="sync-store.myshopify.com",
        shop_domain="sync-store.myshopify.com",
        access_token=encrypt_value("shpat_sync"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return user, workspace, channel


def _transport(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orders.json"):
            state["status_code"] = state.get("status_code", 200)
            if state["status_code"] == 429:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "60"},
                    json={"errors": "throttled"},
                )
            if state["status_code"] == 401:
                return httpx.Response(401, json={"errors": "unauthorized"})
            return httpx.Response(200, json={"orders": state["orders"]})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_order_sync_creates_one_signal_and_cursor_and_is_idempotent(
    db_session,
):
    _user, workspace, channel = await _context(
        db_session,
        "order-sync@example.com",
    )
    state = {"orders": [_order(9001, age_hours=30)]}
    first = await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()
    second = await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()

    signals = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id,
            )
        )
    ).scalars().all()
    works = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalars().all()
    cursor = (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id,
                IntegrationCursor.resource_type == "shopify_orders",
            )
        )
    ).scalar_one()
    assert first["signals_created"] == 1
    assert second["signals_updated"] == 1
    assert len(signals) == 1
    assert len(works) == 1
    assert cursor.cursor_value


@pytest.mark.asyncio
async def test_fulfilled_order_closes_existing_work_item(db_session):
    _user, workspace, channel = await _context(
        db_session,
        "order-sync-resolve@example.com",
    )
    state = {"orders": [_order(9002, age_hours=30)]}
    await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()
    state["orders"] = [_order(9002, fulfillment_status="fulfilled")]
    result = await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()
    signal = (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert result["signals_resolved"] == 1
    assert signal.status == "resolved"
    assert work.status == "succeeded"


@pytest.mark.asyncio
async def test_rate_limit_raises_without_signal_or_cursor(db_session):
    _user, workspace, channel = await _context(
        db_session,
        "order-sync-rate@example.com",
    )
    state = {"orders": [], "status_code": 429}

    with pytest.raises(ShopifyRateLimitError):
        await sync_shopify_order_signals(
            db_session,
            workspace_id=workspace.id,
            channel=channel,
            transport=_transport(state),
        )

    assert (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id
            )
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_order_commerce_reaches_work_item_and_refreshes_on_resync(
    db_session,
):
    """金额、币种、商品图必须落进工作项，改金额后要跟着更新。"""
    _user, workspace, channel = await _context(
        db_session,
        "order-commerce@example.com",
    )
    order = _order(9003, age_hours=30)
    order["total_price"] = "1284.00"
    # 平台返回小写币种是常态，落库前必须归一成大写，否则前端查不到符号。
    order["currency"] = "usd"
    order["line_items"] = [
        {"image": {"src": f"https://cdn.shopify.com/goods-{index}.jpg"}}
        for index in range(5)
    ] + [{"image": None}, {"title": "无图问题"}]
    state = {"orders": [order]}

    await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()

    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    payload = json.loads(work.result_json)
    assert payload["commerce"] == {
        "amount": "1284.00",
        "currency": "USD",
        "order_count": 1,
        # 只留前三张：再多列表行会被挤变形。
        "thumbnails": [
            "https://cdn.shopify.com/goods-0.jpg",
            "https://cdn.shopify.com/goods-1.jpg",
            "https://cdn.shopify.com/goods-2.jpg",
        ],
    }
    # 原有信号字段不能被 commerce 挤掉。
    assert payload["signal_type"] == "order_awaiting_shipment"
    assert payload["source_id"] == "9003"

    state["orders"][0]["total_price"] = "999.00"
    await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()
    await db_session.refresh(work)
    assert json.loads(work.result_json)["commerce"]["amount"] == "999.00"


@pytest.mark.asyncio
async def test_order_without_price_has_no_commerce_block(db_session):
    """历史订单没有金额时不要造假的 0，前端据此降级不显示金额行。"""
    _user, workspace, channel = await _context(
        db_session,
        "order-commerce-empty@example.com",
    )
    state = {"orders": [_order(9004, age_hours=30)]}

    await sync_shopify_order_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport(state),
    )
    await db_session.commit()

    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert "commerce" not in json.loads(work.result_json)
