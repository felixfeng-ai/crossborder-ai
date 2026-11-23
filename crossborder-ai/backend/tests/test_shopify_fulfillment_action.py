"""Shopify 订单履约动作适配器测试。"""

import json
from uuid import uuid4

import httpx
import pytest

from app.core.crypto import encrypt_value
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.shopify_fulfillment_adapter import ShopifyFulfillmentActionAdapter
from app.services.workspaces import ensure_personal_workspace


async def _user_channel(db_session, email: str):
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
        shop_name="fulfillment-store.myshopify.com",
        shop_domain="fulfillment-store.myshopify.com",
        access_token=encrypt_value("shpat_fulfillment"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return user, workspace, channel


def _mock_fulfillment_transport(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/orders/9001/fulfillment_orders.json"):
            return httpx.Response(
                200,
                json={
                    "fulfillment_orders": [
                        {
                            "id": 11,
                            "status": "open",
                            "location_id": 5,
                            "line_items": [
                                {
                                    "id": 101,
                                    "quantity": 2,
                                    "remaining_quantity": 2,
                                }
                            ],
                        }
                    ]
                },
            )
        if path.endswith("/orders/9001/fulfillments.json") or (
            request.method == "POST" and path.endswith("/fulfillments.json")
        ):
            if request.method == "POST":
                state["post_body"] = json.loads(request.content)
                state["fulfillments"].append(
                    {
                        "id": 77,
                        "status": "success",
                        "tracking_number": "TRACK-1",
                        "tracking_company": "UPS",
                    }
                )
                return httpx.Response(
                    201,
                    json={"fulfillment": state["fulfillments"][-1]},
                )
            return httpx.Response(
                200,
                json={"fulfillments": state["fulfillments"]},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fulfillment_preflight_reads_open_fulfillment_order(db_session):
    user, _workspace, channel = await _user_channel(
        db_session,
        "fulfillment-preflight@example.com",
    )
    transport = _mock_fulfillment_transport({"fulfillments": []})
    adapter = ShopifyFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        transport=transport,
    )

    snapshot = await adapter.preflight(
        action_id="orders.fulfill",
        target_id="9001",
        input_data={
            "channel_id": str(channel.id),
            "tracking_number": "TRACK-1",
            "tracking_company": "UPS",
        },
    )

    assert snapshot["order_id"] == "9001"
    assert snapshot["fulfillment_order_ids"] == [11]
    assert snapshot["line_item_count"] == 1
    assert snapshot["duplicate_fulfillment_id"] is None


@pytest.mark.asyncio
async def test_fulfillment_execute_posts_tracking_and_verifies_remote_state(
    db_session,
):
    user, _workspace, channel = await _user_channel(
        db_session,
        "fulfillment-execute@example.com",
    )
    state = {"fulfillments": [], "post_body": None}
    adapter = ShopifyFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        transport=_mock_fulfillment_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "tracking_number": "TRACK-1",
        "tracking_company": "UPS",
        "tracking_url": "https://track.example.com/TRACK-1",
        "notify_customer": True,
    }

    execution = await adapter.execute(
        action_id="orders.fulfill",
        target_id="9001",
        input_data=input_data,
        idempotency_key="fulfillment-action-1",
    )
    verification = await adapter.verify(
        action_id="orders.fulfill",
        target_id="9001",
        execution=execution,
    )

    assert execution.external_id == "77"
    fulfillment = state["post_body"]["fulfillment"]
    assert fulfillment["tracking_info"]["number"] == "TRACK-1"
    assert fulfillment["tracking_info"]["company"] == "UPS"
    assert fulfillment["notify_customer"] is True
    line_item = fulfillment["line_items_by_fulfillment_order"][0]
    assert line_item["fulfillment_order_id"] == 11
    assert line_item["fulfillment_order_line_items"] == [
        {"id": 101, "quantity": 2}
    ]
    assert verification.matched is True
    assert verification.snapshot["tracking_number"] == "TRACK-1"


@pytest.mark.asyncio
async def test_fulfillment_duplicate_tracking_is_idempotent(db_session):
    user, _workspace, channel = await _user_channel(
        db_session,
        "fulfillment-duplicate@example.com",
    )
    state = {
        "fulfillments": [
            {
                "id": 88,
                "status": "success",
                "tracking_number": "TRACK-DUP",
                "tracking_company": "UPS",
            }
        ],
        "post_body": None,
    }
    adapter = ShopifyFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        transport=_mock_fulfillment_transport(state),
    )

    execution = await adapter.execute(
        action_id="orders.fulfill",
        target_id="9001",
        input_data={
            "channel_id": str(channel.id),
            "tracking_number": "TRACK-DUP",
            "tracking_company": "UPS",
        },
        idempotency_key="fulfillment-duplicate-1",
    )

    assert execution.external_id == "88"
    assert execution.output["replayed"] is True
    assert state["post_body"] is None


@pytest.mark.asyncio
async def test_fulfillment_requires_tracking_company(db_session):
    user, _workspace, channel = await _user_channel(
        db_session,
        "fulfillment-company@example.com",
    )
    adapter = ShopifyFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        transport=_mock_fulfillment_transport({"fulfillments": []}),
    )

    with pytest.raises(ValueError, match="承运商"):
        await adapter.preflight(
            action_id="orders.fulfill",
            target_id="9001",
            input_data={
                "channel_id": str(channel.id),
                "tracking_number": "TRACK-1",
            },
        )
