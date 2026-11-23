"""客户会话与 Shopify 订单事实关联测试。"""

import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_work import WorkItem
from app.models.agent_task import AgentTask
from app.models.action_run import ActionRun
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerOrderLink,
    CustomerThread,
    ReplyDraft,
)
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.customer_order_link import (
    ShopifyOrderFact,
    ShopifyOrderFactsClient,
    apply_customer_order_selection,
    link_customer_order,
    resolve_customer_order,
)
from app.services.workspaces import ensure_personal_workspace


class FakeOrderClient:
    def __init__(self, orders_by_channel=None):
        self.orders_by_channel = orders_by_channel or {}
        self.calls = []

    async def find_orders(self, *, shopify_channel, customer_email):
        self.calls.append(
            {
                "channel_id": shopify_channel.id,
                "email": customer_email,
            }
        )
        return self.orders_by_channel.get(shopify_channel.id, [])


async def _context(
    db_session,
    email: str,
    *,
    shop_count: int = 1,
):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        provider="imap_smtp",
        external_account_id="support@example.com",
        display_name="客服邮箱",
        credentials_ciphertext=encrypt_value("{}"),
    )
    db_session.add(channel)
    await db_session.flush()
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id=f"order-thread-{user.id}",
        thread_type="direct_message",
        customer_address_ciphertext=encrypt_value("buyer@example.com"),
        customer_email_hash="buyer-hash",
        subject="Where is my order?",
        language="en",
    )
    db_session.add(thread)
    shops = []
    for index in range(shop_count):
        shop = ShopifyChannel(
            user_id=user.id,
            workspace_id=workspace.id,
            shop_name=f"order-shop-{index}",
            shop_domain=f"order-shop-{index}.myshopify.com",
            access_token=encrypt_value(f"token-{index}"),
            is_active=True,
        )
        db_session.add(shop)
        shops.append(shop)
    await db_session.commit()
    await db_session.refresh(thread)
    for shop in shops:
        await db_session.refresh(shop)
    return user, workspace, channel, thread, shops


def _fact(order_id: str = "1001", name: str = "#1001") -> ShopifyOrderFact:
    return ShopifyOrderFact(
        shopify_channel_id="",
        external_order_id=order_id,
        order_name=name,
        financial_status="paid",
        fulfillment_status="fulfilled",
        order_created_at=None,
        tracking_company="UPS",
        tracking_number="1Z999",
        tracking_url="https://tracking.example.com/1Z999",
        snapshot={"id": int(order_id), "name": name},
    )


@pytest.mark.asyncio
async def test_resolver_links_single_order_and_is_idempotent(db_session):
    _user, workspace, _channel, thread, shops = await _context(
        db_session,
        "order-link-single@example.com",
    )
    fact = _fact()
    client = FakeOrderClient({shops[0].id: [fact]})

    first = await resolve_customer_order(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        client=client,
    )
    await db_session.commit()
    second = await resolve_customer_order(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        client=client,
    )
    await db_session.commit()

    link = (
        await db_session.execute(
            select(CustomerOrderLink).where(
                CustomerOrderLink.thread_id == thread.id
            )
        )
    ).scalar_one()
    await db_session.refresh(thread)
    assert first.status == "linked"
    assert second.status == "linked"
    assert thread.related_order_id == "1001"
    assert link.order_name == "#1001"
    assert link.tracking_number == "1Z999"
    assert link.shopify_channel_id == shops[0].id
    assert client.calls == [
        {"channel_id": shops[0].id, "email": "buyer@example.com"},
        {"channel_id": shops[0].id, "email": "buyer@example.com"},
    ]


@pytest.mark.asyncio
async def test_resolver_refuses_ambiguous_orders(db_session):
    _user, workspace, _channel, thread, shops = await _context(
        db_session,
        "order-link-ambiguous@example.com",
        shop_count=2,
    )
    client = FakeOrderClient(
        {
            shops[0].id: [_fact("1001", "#1001")],
            shops[1].id: [_fact("1002", "#1002")],
        }
    )

    result = await resolve_customer_order(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        client=client,
    )
    await db_session.commit()
    await db_session.refresh(thread)

    assert result.status == "ambiguous"
    assert result.candidate_count == 2
    assert len(result.candidates) == 2
    assert {
        item["external_order_id"] for item in result.candidates
    } == {"1001", "1002"}
    assert "buyer@example.com" not in json.dumps(result.candidates)
    assert thread.related_order_id is None


@pytest.mark.asyncio
async def test_seller_can_select_one_ambiguous_order_candidate(db_session):
    _user, workspace, _channel, thread, shops = await _context(
        db_session,
        "order-link-select@example.com",
        shop_count=2,
    )
    client = FakeOrderClient(
        {
            shops[0].id: [_fact("1001", "#1001")],
            shops[1].id: [_fact("1002", "#1002")],
        }
    )

    selected = await link_customer_order(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        shopify_channel_id=shops[1].id,
        external_order_id="1002",
        client=client,
    )
    await db_session.commit()
    await db_session.refresh(thread)
    link = (
        await db_session.execute(
            select(CustomerOrderLink).where(
                CustomerOrderLink.thread_id == thread.id
            )
        )
    ).scalar_one()

    assert selected.status == "linked"
    assert thread.related_order_id == "1002"
    assert link.external_order_id == "1002"
    assert link.shopify_channel_id == shops[1].id


@pytest.mark.asyncio
async def test_resolver_only_queries_current_workspace(db_session):
    _user, workspace, _channel, thread, shops = await _context(
        db_session,
        "order-link-scope@example.com",
    )
    _other_user, _other_workspace, _other_channel, _other_thread, other_shops = (
        await _context(
            db_session,
            "order-link-other@example.com",
        )
    )
    client = FakeOrderClient({shops[0].id: [_fact()]})

    await resolve_customer_order(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        client=client,
    )
    await db_session.commit()

    assert {call["channel_id"] for call in client.calls} == {shops[0].id}
    assert other_shops[0].id not in {
        call["channel_id"] for call in client.calls
    }


@pytest.mark.asyncio
async def test_resolver_without_shopify_channel_is_safe(db_session):
    _user, workspace, _channel, thread, _shops = await _context(
        db_session,
        "order-link-none@example.com",
        shop_count=0,
    )

    result = await resolve_customer_order(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        client=FakeOrderClient(),
    )

    assert result.status == "no_channel"
    assert result.candidate_count == 0


@pytest.mark.asyncio
async def test_shopify_order_client_reads_order_and_tracking():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/fulfillments.json"):
            return httpx.Response(
                200,
                json={
                    "fulfillments": [
                        {
                            "tracking_company": "UPS",
                            "tracking_number": "1Z999",
                            "tracking_url": "https://tracking.example.com/1Z999",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "orders": [
                    {
                        "id": 1001,
                        "name": "#1001",
                        "email": "buyer@example.com",
                        "financial_status": "paid",
                        "fulfillment_status": "fulfilled",
                        "created_at": "2026-11-20T01:00:00Z",
                    }
                ]
            },
        )

    channel = ShopifyChannel(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        shop_name="client-shop",
        shop_domain="client-shop.myshopify.com",
        access_token=encrypt_value("shpat_test"),
        is_active=True,
    )
    client = ShopifyOrderFactsClient(
        transport=httpx.MockTransport(handler)
    )

    orders = await client.find_orders(
        shopify_channel=channel,
        customer_email="Buyer@Example.com",
    )

    assert len(orders) == 1
    assert orders[0].external_order_id == "1001"
    assert orders[0].tracking_number == "1Z999"
    assert requests[0].url.params["email"] == "buyer@example.com"
    assert requests[0].headers["X-Shopify-Access-Token"] == "shpat_test"


@pytest.mark.asyncio
async def test_selecting_order_invalidates_old_draft_and_requeues_work(db_session):
    user, workspace, channel, thread, shops = await _context(
        db_session,
        "order-link-switch@example.com",
    )
    thread.related_order_id = "1001"
    db_session.add(
        CustomerOrderLink(
            workspace_id=workspace.id,
            thread_id=thread.id,
            shopify_channel_id=shops[0].id,
            external_order_id="1001",
            order_name="#1001",
            snapshot_json="{}",
        )
    )
    db_session.add(
        CustomerMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            external_message_id="<order-switch@example.com>",
            direction="inbound",
            body_text="Where is my order?",
            send_status="received",
        )
    )
    draft = ReplyDraft(
        workspace_id=workspace.id,
        thread_id=thread.id,
        version=1,
        language="en",
        body_text="Old order reply",
        status="ready",
    )
    item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="选择订单",
        summary="有多个订单",
        status="waiting_user",
        requires_action="choose",
        source_type="customer_thread",
        source_id=str(thread.id),
        result_json=json.dumps(
            {
                "order_lookup_status": "ambiguous",
                "order_candidates": [
                    {"external_order_id": "1002", "order_name": "#1002"}
                ],
            }
        ),
    )
    db_session.add_all([draft, item])
    await db_session.flush()
    action = ActionRun(
        workspace_id=workspace.id,
        work_item_id=item.id,
        action_id="messages.reply",
        platform="email",
        target_type="conversation",
        target_id=str(thread.id),
        input_json=json.dumps(
            {
                "channel_id": str(channel.id),
                "thread_id": str(thread.id),
                "draft_id": str(draft.id),
            }
        ),
        status="awaiting_confirmation",
        risk_level="medium",
        autonomy_level="confirm",
        idempotency_key="old-order-reply",
        policy_snapshot_json="{}",
    )
    old_task = AgentTask(
        user_id=user.id,
        task_type="customer_reply",
        status="succeeded",
        input="{}",
        idempotency_key="old-task",
        cost=0,
    )
    db_session.add_all([action, old_task])
    await db_session.commit()
    client = FakeOrderClient({shops[0].id: [_fact("1002", "#1002")]})

    result = await apply_customer_order_selection(
        db_session,
        workspace_id=workspace.id,
        thread=thread,
        work_item=item,
        shopify_channel_id=shops[0].id,
        external_order_id="1002",
        client=client,
    )
    await db_session.commit()

    await db_session.refresh(thread)
    await db_session.refresh(item)
    await db_session.refresh(draft)
    await db_session.refresh(action)
    tasks = (
        await db_session.execute(
            select(AgentTask).where(AgentTask.user_id == user.id)
        )
    ).scalars().all()
    assert result.status == "linked"
    assert thread.related_order_id == "1002"
    assert draft.status == "stale"
    assert action.status == "cancelled"
    assert item.status == "running"
    assert item.requires_action == "none"
    assert any(task.status == "pending" for task in tasks)


@pytest.mark.asyncio
async def test_work_item_detail_exposes_linked_order_fact_without_email(
    client,
    db_session,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "order-context@example.com",
            "username": "order-context",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "order-context@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        provider="imap_smtp",
        external_account_id="support@example.com",
        display_name="客服邮箱",
        credentials_ciphertext=encrypt_value("{}"),
    )
    db_session.add(channel)
    await db_session.flush()
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="order-context-thread",
        thread_type="direct_message",
        customer_address_ciphertext=encrypt_value("private@example.com"),
        subject="Order status",
        language="en",
        related_order_id="1001",
    )
    db_session.add(thread)
    await db_session.flush()
    message = CustomerMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        external_message_id="<order-context@example.com>",
        direction="inbound",
        body_text="Where is my order?",
        send_status="received",
    )
    db_session.add(message)
    db_session.add(
        CustomerOrderLink(
            workspace_id=workspace.id,
            thread_id=thread.id,
            external_order_id="1001",
            order_name="#1001",
            financial_status="paid",
            fulfillment_status="fulfilled",
            tracking_company="UPS",
            tracking_number="1Z999",
            tracking_url="https://tracking.example.com/1Z999",
            snapshot_json="{}",
        )
    )
    item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="订单状态",
        summary="已关联订单",
        status="waiting_user",
        requires_action="none",
        source_type="customer_thread",
        source_id=str(thread.id),
    )
    db_session.add(item)
    await db_session.commit()

    detail = await client.get(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/work-items/{item.id}"
        ),
        headers=headers,
    )

    assert detail.status_code == 200
    order = detail.json()["customer_context"]["order"]
    assert order == {
        "order_name": "#1001",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "tracking_company": "UPS",
        "tracking_number": "1Z999",
        "tracking_url": "https://tracking.example.com/1Z999",
    }
    assert "private@example.com" not in detail.text


@pytest.mark.asyncio
async def test_customer_order_selection_endpoint_requeues_reply(
    client,
    db_session,
    monkeypatch,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "order-select-api@example.com",
            "username": "order-select-api",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "order-select-api@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        provider="imap_smtp",
        external_account_id="support@example.com",
        display_name="客服邮箱",
        credentials_ciphertext=encrypt_value("{}"),
    )
    shop = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="select-api-shop",
        shop_domain="select-api-shop.myshopify.com",
        access_token=encrypt_value("shpat_select"),
        is_active=True,
    )
    db_session.add_all([channel, shop])
    await db_session.flush()
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="select-api-thread",
        thread_type="direct_message",
        customer_address_ciphertext=encrypt_value("buyer@example.com"),
        subject="Choose order",
        language="en",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        CustomerMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            external_message_id="<select-api@example.com>",
            direction="inbound",
            body_text="Where is my order?",
            send_status="received",
        )
    )
    item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="选择订单",
        summary="多个订单",
        status="waiting_user",
        requires_action="choose",
        source_type="customer_thread",
        source_id=str(thread.id),
        result_json=json.dumps(
            {
                "order_lookup_status": "ambiguous",
                "order_candidates": [
                    {
                        "shopify_channel_id": str(shop.id),
                        "external_order_id": "5001",
                        "order_name": "#5001",
                    }
                ],
            }
        ),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(shop)

    class FakeClient:
        async def find_orders(self, *, shopify_channel, customer_email):
            return [_fact("5001", "#5001")]

    monkeypatch.setattr(
        "app.services.customer_order_link.ShopifyOrderFactsClient",
        lambda: FakeClient(),
    )
    detail = await client.get(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/work-items/{item.id}"
        ),
        headers=headers,
    )
    selected = await client.post(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/customer-threads/{thread.id}/orders/link"
        ),
        headers=headers,
        json={
            "shopify_channel_id": str(shop.id),
            "external_order_id": "5001",
        },
    )

    assert selected.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["customer_context"]["order_candidates"][0][
        "external_order_id"
    ] == "5001"
    assert selected.json()["status"] == "linked"
    assert selected.json()["order"]["order_name"] == "#5001"
    pending_tasks = (
        await db_session.execute(
            select(AgentTask).where(
                AgentTask.user_id == user.id,
                AgentTask.status == "pending",
            )
        )
    ).scalars().all()
    assert len(pending_tasks) == 1
