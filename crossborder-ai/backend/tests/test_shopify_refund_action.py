"""Shopify 退款动作适配器测试。"""

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from app.core.crypto import encrypt_value
from app.models.action_run import ActionRun
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.shopify_refund_adapter import ShopifyRefundActionAdapter
from app.services.work_items import create_work_item
from app.services.workspaces import ensure_personal_workspace


async def _refund_context(db_session, email: str):
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
        shop_name="refund-store.myshopify.com",
        shop_domain="refund-store.myshopify.com",
        access_token=encrypt_value("shpat_refund"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return user, workspace, channel


def _refund_transport(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/orders/9002.json"):
            return httpx.Response(
                200,
                json={
                    "order": {
                        "id": 9002,
                        "total_price": "80.00",
                        "current_total_price": "80.00",
                        "currency": "USD",
                        "payment_gateway_names": ["shopify_payments"],
                    }
                },
            )
        if path.endswith("/orders/9002/refunds.json"):
            if request.method == "POST":
                body = json.loads(request.content)
                state["post_body"] = body
                refund = {
                    "id": 7002,
                    "note": body["refund"].get("note"),
                    "transactions": body["refund"].get("transactions", []),
                }
                state["refunds"].append(refund)
                return httpx.Response(201, json={"refund": refund})
            return httpx.Response(
                200,
                json={"refunds": state["refunds"]},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_refund_preflight_accepts_amount_within_refundable_balance(
    db_session,
):
    user, _workspace, channel = await _refund_context(
        db_session,
        "refund-preflight@example.com",
    )
    adapter = ShopifyRefundActionAdapter(
        db_session,
        user_id=user.id,
        transport=_refund_transport({"refunds": []}),
    )

    snapshot = await adapter.preflight(
        action_id="refunds.create",
        target_id="9002",
        input_data={
            "channel_id": str(channel.id),
            "amount": 30,
            "reason": "customer requested partial refund",
        },
    )

    assert snapshot["order_id"] == "9002"
    assert snapshot["refundable_amount"] == 80.0
    assert snapshot["amount"] == 30.0


@pytest.mark.asyncio
async def test_refund_preflight_rejects_amount_above_remaining_balance(
    db_session,
):
    user, _workspace, channel = await _refund_context(
        db_session,
        "refund-over@example.com",
    )
    adapter = ShopifyRefundActionAdapter(
        db_session,
        user_id=user.id,
        transport=_refund_transport({"refunds": []}),
    )

    with pytest.raises(ValueError, match="可退金额"):
        await adapter.preflight(
            action_id="refunds.create",
            target_id="9002",
            input_data={
                "channel_id": str(channel.id),
                "amount": 90,
            },
        )


@pytest.mark.asyncio
async def test_refund_execute_and_verify_are_idempotent_by_marker(db_session):
    user, _workspace, channel = await _refund_context(
        db_session,
        "refund-execute@example.com",
    )
    state = {"refunds": [], "post_body": None}
    adapter = ShopifyRefundActionAdapter(
        db_session,
        user_id=user.id,
        transport=_refund_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "amount": 30,
        "reason": "customer requested partial refund",
        "notify_customer": True,
    }

    execution = await adapter.execute(
        action_id="refunds.create",
        target_id="9002",
        input_data=input_data,
        idempotency_key="refund-action-1",
    )
    verification = await adapter.verify(
        action_id="refunds.create",
        target_id="9002",
        execution=execution,
    )

    assert execution.external_id == "7002"
    assert state["post_body"]["refund"]["transactions"][0]["amount"] == "30.00"
    assert "refund-action-1" in state["post_body"]["refund"]["note"]
    assert verification.matched is True
    assert verification.snapshot["amount"] == 30.0

    replay = await adapter.execute(
        action_id="refunds.create",
        target_id="9002",
        input_data=input_data,
        idempotency_key="refund-action-1",
    )
    assert replay.external_id == "7002"
    assert replay.output["replayed"] is True
    assert len(state["refunds"]) == 1


@pytest.mark.asyncio
async def test_refund_preflight_uses_durable_daily_total(db_session):
    user, workspace, channel = await _refund_context(
        db_session,
        "refund-daily@example.com",
    )
    work_item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="refund_action",
        source="agent",
        title="历史退款",
        summary="用于测试单日退款上限",
    )
    previous = ActionRun(
        workspace_id=workspace.id,
        work_item_id=work_item.id,
        action_id="refunds.create",
        platform="shopify",
        target_type="order",
        target_id="9001",
        input_json="{}",
        status="succeeded",
        risk_level="high",
        autonomy_level="confirm",
        idempotency_key="old-refund-1",
        confirmed_by_user_id=user.id,
        after_snapshot_json=json.dumps({"amount": 280.0}),
        finished_at=datetime.now(timezone.utc),
    )
    # 这里只验证适配器会读取持久化动作记录，不触发外键级联的业务执行。
    db_session.add(previous)
    await db_session.commit()
    adapter = ShopifyRefundActionAdapter(
        db_session,
        user_id=user.id,
        transport=_refund_transport({"refunds": []}),
    )

    with pytest.raises(ValueError, match="单日"):
        await adapter.preflight(
            action_id="refunds.create",
            target_id="9002",
            input_data={
                "channel_id": str(channel.id),
                "amount": 30,
            },
        )
