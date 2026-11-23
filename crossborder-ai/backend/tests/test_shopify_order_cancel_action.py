"""Shopify 订单取消动作测试。"""

import json
from uuid import uuid4

import httpx
import pytest

from app.core.crypto import encrypt_value
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.models.action_run import ActionRun
from app.services.action_dispatcher import resolve_action_adapter
from app.services.shopify_order_cancel_adapter import (
    ShopifyOrderCancelActionAdapter,
)
from app.services.workspaces import ensure_personal_workspace


async def _channel_context(db_session, email: str):
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
        shop_name="cancel-store.myshopify.com",
        shop_domain="cancel-store.myshopify.com",
        access_token=encrypt_value("shpat_cancel"),
    )
    db_session.add(channel)
    await db_session.commit()
    return user, workspace, channel


def _transport(state: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/orders/9100.json"):
            return httpx.Response(200, json={"order": state["order"]})
        if request.method == "POST" and path.endswith("/orders/9100/cancel.json"):
            body = json.loads(request.content)
            state["cancel_body"] = body
            state["cancel_posts"] += 1
            state["order"] = {
                **state["order"],
                "cancelled_at": "2026-11-19T10:00:00Z",
                "cancel_reason": body.get("reason"),
            }
            return httpx.Response(200, json={"order": state["order"]})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_order_cancel_preflights_executes_and_verifies(db_session):
    user, workspace, channel = await _channel_context(
        db_session,
        "order-cancel@example.com",
    )
    state = {
        "order": {
            "id": 9100,
            "cancelled_at": None,
            "fulfillment_status": None,
            "financial_status": "paid",
            "email": "buyer@example.com",
        },
        "cancel_body": None,
        "cancel_posts": 0,
    }
    adapter = ShopifyOrderCancelActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "reason": "customer",
        "restock": True,
        "refund": False,
        "notify_customer": True,
    }

    snapshot = await adapter.preflight(
        action_id="orders.cancel",
        target_id="9100",
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="orders.cancel",
        target_id="9100",
        input_data=input_data,
        idempotency_key="cancel-order-1",
    )
    verification = await adapter.verify(
        action_id="orders.cancel",
        target_id="9100",
        execution=execution,
    )

    assert snapshot["order_id"] == "9100"
    assert snapshot["already_cancelled"] is False
    assert state["cancel_body"] == {
        "reason": "customer",
        "email": "buyer@example.com",
        "restock": True,
        "refund": False,
    }
    assert state["cancel_posts"] == 1
    assert verification.matched is True
    assert verification.snapshot["cancelled_at"]


@pytest.mark.asyncio
async def test_order_cancel_replays_when_already_cancelled(db_session):
    user, workspace, channel = await _channel_context(
        db_session,
        "order-cancel-replay@example.com",
    )
    state = {
        "order": {
            "id": 9100,
            "cancelled_at": "2026-11-19T09:00:00Z",
            "fulfillment_status": None,
            "financial_status": "voided",
            "email": "buyer@example.com",
        },
        "cancel_body": None,
        "cancel_posts": 0,
    }
    adapter = ShopifyOrderCancelActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )

    execution = await adapter.execute(
        action_id="orders.cancel",
        target_id="9100",
        input_data={
            "channel_id": str(channel.id),
            "reason": "customer",
        },
        idempotency_key="cancel-order-replay-1",
    )

    assert execution.output["replayed"] is True
    assert state["cancel_posts"] == 0


@pytest.mark.asyncio
async def test_order_cancel_rejects_fulfilled_order(db_session):
    user, workspace, channel = await _channel_context(
        db_session,
        "order-cancel-fulfilled@example.com",
    )
    state = {
        "order": {
            "id": 9100,
            "cancelled_at": None,
            "fulfillment_status": "fulfilled",
            "financial_status": "paid",
            "email": "buyer@example.com",
        },
        "cancel_body": None,
        "cancel_posts": 0,
    }
    adapter = ShopifyOrderCancelActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )

    with pytest.raises(ValueError, match="已履约"):
        await adapter.preflight(
            action_id="orders.cancel",
            target_id="9100",
            input_data={"channel_id": str(channel.id)},
        )


@pytest.mark.asyncio
async def test_order_cancel_requires_email_when_notifying_buyer(db_session):
    user, workspace, channel = await _channel_context(
        db_session,
        "order-cancel-email@example.com",
    )
    state = {
        "order": {
            "id": 9100,
            "cancelled_at": None,
            "fulfillment_status": None,
            "financial_status": "paid",
            "email": "",
        },
        "cancel_body": None,
        "cancel_posts": 0,
    }
    adapter = ShopifyOrderCancelActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )

    with pytest.raises(ValueError, match="买家邮箱"):
        await adapter.preflight(
            action_id="orders.cancel",
            target_id="9100",
            input_data={
                "channel_id": str(channel.id),
                "notify_customer": True,
            },
        )


@pytest.mark.asyncio
async def test_dispatcher_routes_order_cancel_action(db_session):
    user, workspace, _channel = await _channel_context(
        db_session,
        "order-cancel-dispatch@example.com",
    )
    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=uuid4(),
        action_id="orders.cancel",
        platform="shopify",
        target_type="order",
        target_id="9100",
        input_json="{}",
        status="queued",
        risk_level="high",
        autonomy_level="confirm",
        idempotency_key="order-cancel-dispatch-1",
    )

    adapter = await resolve_action_adapter(db_session, run)

    assert isinstance(adapter, ShopifyOrderCancelActionAdapter)
