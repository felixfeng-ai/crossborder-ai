"""Agent 客服自动值班队列与草稿生成测试。"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.crypto import encrypt_value
from app.models.action_run import ActionRun
from app.models.agent_policy import AgentAutonomyPolicy
from app.models.agent_task import AgentTask
from app.models.agent_work import WorkItem
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerOrderLink,
    CustomerThread,
    ReplyDraft,
)
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.customer_reply_worker import (
    enqueue_customer_reply_tasks,
    process_customer_reply_work_item,
)
from app.services.customer_order_link import ShopifyOrderFact
from app.services import agent_task_executor
from app.services.workspaces import ensure_personal_workspace


class FakeReplyGenerator:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return (
            "Thanks for reaching out. We have received your message "
            "and will help you with the next step."
        )


async def _context(
    db_session,
    email: str,
    *,
    body: str = "Could you tell me when my parcel will arrive?",
    risk: str = "low",
    assigned: bool = False,
    with_link: bool = False,
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
        external_thread_id=f"thread-{user.id}",
        thread_type="direct_message",
        customer_address_ciphertext=encrypt_value("buyer@example.com"),
        subject="Where is my parcel?",
        language="en",
        status="waiting_user",
        priority="urgent" if risk == "high" else "normal",
        assigned_user_id=user.id if assigned else None,
        related_order_id="order-1" if with_link else None,
    )
    db_session.add(thread)
    await db_session.flush()
    if with_link:
        db_session.add(
            CustomerOrderLink(
                workspace_id=workspace.id,
                thread_id=thread.id,
                shopify_channel_id=None,
                external_order_id="order-1",
                order_name="#1001",
                financial_status="paid",
                fulfillment_status="fulfilled",
                tracking_company="UPS",
                tracking_number="1Z999",
                tracking_url="https://tracking.example.com/1Z999",
                snapshot_json=json.dumps({"name": "#1001"}),
            )
        )
    message = CustomerMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        external_message_id=f"<message-{user.id}@example.com>",
        direction="inbound",
        body_text=body,
        language="en",
        send_status="received",
    )
    db_session.add(message)
    item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="客户询问物流",
        summary="客户新消息已同步",
        status="running",
        requires_action="none",
        current_step="Agent 正在读取客户消息",
        source_type="customer_thread",
        source_id=str(thread.id),
        result_json=json.dumps(
            {
                "intent": "shipping",
                "risk_level": risk,
                "requires_human": risk == "high",
                "auto_reply_candidate": risk == "low",
            }
        ),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return user, workspace, channel, thread, message, item


@pytest.mark.asyncio
async def test_worker_enqueues_running_customer_reply_once(db_session):
    _user, workspace, _channel, thread, _message, item = await _context(
        db_session,
        "duty-enqueue@example.com",
    )
    high_item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="高风险",
        summary="等待人工接管",
        status="waiting_user",
        requires_action="none",
        source_type="customer_thread",
        source_id=str(thread.id),
        result_json=json.dumps(
            {
                "intent": "complaint",
                "risk_level": "high",
                "requires_human": True,
            }
        ),
    )
    db_session.add(high_item)
    await db_session.commit()

    first = await enqueue_customer_reply_tasks(db_session)
    second = await enqueue_customer_reply_tasks(db_session)
    await db_session.commit()

    all_tasks = (
        await db_session.execute(select(AgentTask))
    ).scalars().all()
    assert first == 1
    assert second == 0
    assert len(all_tasks) == 1
    task = all_tasks[0]
    assert task.task_type == "customer_reply"
    assert task.workspace_id == workspace.id
    assert task.cost == 0
    params = json.loads(task.input)
    assert params["work_item_id"] == str(item.id)
    assert params["workspace_id"] == str(workspace.id)


@pytest.mark.asyncio
async def test_worker_generates_draft_and_confirmation_action(db_session):
    _user, workspace, channel, thread, message, item = await _context(
        db_session,
        "duty-draft@example.com",
        body="Do you have this in blue?",
        with_link=True,
    )
    generator = FakeReplyGenerator()

    result = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=generator,
    )
    await db_session.commit()

    drafts = (
        await db_session.execute(
            select(ReplyDraft).where(
                ReplyDraft.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert result["status"] == "awaiting_confirmation"
    assert len(drafts) == 1
    assert drafts[0].body_text.startswith("Thanks for reaching out")
    assert drafts[0].language == "en"
    assert generator.calls[0]["customer_message"] == message.body_text
    assert generator.calls[0]["facts"]["order_fact"]["tracking_number"] == "1Z999"
    assert run.action_id == "messages.reply"
    assert run.status == "awaiting_confirmation"
    assert run.target_id == str(thread.id)
    await db_session.refresh(item)
    assert item.requires_action == "confirm"


@pytest.mark.asyncio
async def test_worker_auto_queues_low_risk_reply_when_policy_allows(db_session):
    _user, workspace, _channel, _thread, _message, item = await _context(
        db_session,
        "duty-auto@example.com",
        body="Do you ship to Germany?",
        with_link=True,
    )
    db_session.add(
        AgentAutonomyPolicy(
            workspace_id=workspace.id,
            action_id="messages.reply",
            autonomy_level="auto",
            conditions_json="{}",
            enabled=True,
        )
    )
    await db_session.commit()

    result = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=FakeReplyGenerator(),
    )
    await db_session.commit()

    run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert result["status"] == "queued"
    assert run.status == "queued"
    assert run.autonomy_level == "auto"


@pytest.mark.asyncio
async def test_worker_without_order_fact_requires_confirmation(db_session):
    _user, workspace, _channel, _thread, _message, item = await _context(
        db_session,
        "duty-no-order@example.com",
        body="Where is my order?",
        with_link=False,
    )
    db_session.add(
        AgentAutonomyPolicy(
            workspace_id=workspace.id,
            action_id="messages.reply",
            autonomy_level="auto",
            conditions_json="{}",
            enabled=True,
        )
    )
    await db_session.commit()

    result = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=FakeReplyGenerator(),
    )
    await db_session.commit()

    run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert result["status"] == "awaiting_confirmation"
    assert run.status == "awaiting_confirmation"
    assert run.autonomy_level == "confirm"


@pytest.mark.asyncio
async def test_worker_resolves_unique_shopify_order_before_auto_reply(
    db_session,
):
    _user, workspace, _channel, thread, _message, item = await _context(
        db_session,
        "duty-resolve-order@example.com",
        body="Where is my order?",
        with_link=False,
    )
    shop = ShopifyChannel(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        shop_name="duty-shop",
        shop_domain="duty-shop.myshopify.com",
        access_token=encrypt_value("shpat_duty"),
        is_active=True,
    )
    db_session.add(shop)
    db_session.add(
        AgentAutonomyPolicy(
            workspace_id=workspace.id,
            action_id="messages.reply",
            autonomy_level="auto",
            conditions_json="{}",
            enabled=True,
        )
    )
    await db_session.commit()
    await db_session.refresh(shop)

    class WorkerOrderClient:
        async def find_orders(self, *, shopify_channel, customer_email):
            assert shopify_channel.id == shop.id
            assert customer_email == "buyer@example.com"
            return [
                ShopifyOrderFact(
                    shopify_channel_id=str(shop.id),
                    external_order_id="3001",
                    order_name="#3001",
                    financial_status="paid",
                    fulfillment_status="fulfilled",
                    order_created_at=None,
                    tracking_company="DHL",
                    tracking_number="DHL123",
                    tracking_url="https://tracking.example.com/DHL123",
                    snapshot={"name": "#3001"},
                )
            ]

    generator = FakeReplyGenerator()
    result = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=generator,
        order_client=WorkerOrderClient(),
    )
    await db_session.commit()

    await db_session.refresh(thread)
    run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert result["status"] == "queued"
    assert thread.related_order_id == "3001"
    assert generator.calls[0]["facts"]["order_fact"]["tracking_number"] == "DHL123"
    assert run.autonomy_level == "auto"


@pytest.mark.asyncio
async def test_worker_pauses_for_order_choice_when_candidates_are_ambiguous(
    db_session,
):
    _user, workspace, _channel, _thread, _message, item = await _context(
        db_session,
        "duty-order-choice@example.com",
        body="Where is my order?",
        with_link=False,
    )
    shops = [
        ShopifyChannel(
            user_id=workspace.owner_user_id,
            workspace_id=workspace.id,
            shop_name=f"choice-{index}",
            shop_domain=f"choice-{index}.myshopify.com",
            access_token=encrypt_value(f"shpat_choice_{index}"),
            is_active=True,
        )
        for index in range(2)
    ]
    db_session.add_all(shops)
    await db_session.commit()
    for shop in shops:
        await db_session.refresh(shop)

    class AmbiguousOrderClient:
        async def find_orders(self, *, shopify_channel, customer_email):
            index = shops.index(shopify_channel)
            return [
                ShopifyOrderFact(
                    shopify_channel_id=str(shopify_channel.id),
                    external_order_id=str(4000 + index),
                    order_name=f"#{4000 + index}",
                    financial_status="paid",
                    fulfillment_status="fulfilled",
                    order_created_at=None,
                    tracking_company="UPS",
                    tracking_number=f"TRACK-{index}",
                    tracking_url=None,
                    snapshot={"name": f"#{4000 + index}"},
                )
            ]

    generator = FakeReplyGenerator()
    result = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=generator,
        order_client=AmbiguousOrderClient(),
    )
    await db_session.commit()

    await db_session.refresh(item)
    drafts = (
        await db_session.execute(
            select(ReplyDraft).where(
                ReplyDraft.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    runs = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    stored_result = json.loads(item.result_json)
    assert result["status"] == "choose_order"
    assert item.status == "waiting_user"
    assert item.requires_action == "choose"
    assert len(stored_result["order_candidates"]) == 2
    assert "buyer@example.com" not in item.result_json
    assert drafts == []
    assert runs == []
    assert generator.calls == []


@pytest.mark.asyncio
async def test_worker_is_idempotent_for_same_customer_message(db_session):
    _user, workspace, _channel, _thread, _message, item = await _context(
        db_session,
        "duty-idempotent@example.com",
    )
    generator = FakeReplyGenerator()

    first = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=generator,
    )
    await db_session.commit()
    second = await process_customer_reply_work_item(
        db_session,
        work_item_id=item.id,
        generator=generator,
    )
    await db_session.commit()

    drafts = (
        await db_session.execute(
            select(ReplyDraft).where(
                ReplyDraft.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    runs = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    assert first["status"] == "awaiting_confirmation"
    assert second["status"] == "awaiting_confirmation"
    assert len(generator.calls) == 1
    assert len(drafts) == 1
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_worker_skips_human_takeover_and_high_risk(db_session):
    _user, _workspace, _channel, _thread, _message, assigned_item = (
        await _context(
            db_session,
            "duty-assigned@example.com",
            assigned=True,
        )
    )
    _user2, _workspace2, _channel2, _thread2, _message2, high_item = (
        await _context(
            db_session,
            "duty-high@example.com",
            risk="high",
            body="I will contact my lawyer.",
        )
    )
    generator = FakeReplyGenerator()

    assigned = await process_customer_reply_work_item(
        db_session,
        work_item_id=assigned_item.id,
        generator=generator,
    )
    high = await process_customer_reply_work_item(
        db_session,
        work_item_id=high_item.id,
        generator=generator,
    )
    await db_session.commit()

    assert assigned["status"] == "manual_takeover"
    assert high["status"] == "requires_human"
    assert generator.calls == []


@pytest.mark.asyncio
async def test_agent_task_executor_runs_customer_reply_worker(
    db_session,
    monkeypatch,
):
    _user, workspace, _channel, _thread, _message, item = await _context(
        db_session,
        "duty-executor@example.com",
    )
    assert await enqueue_customer_reply_tasks(db_session) == 1
    await db_session.commit()
    task = (
        await db_session.execute(select(AgentTask))
    ).scalar_one()
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    await db_session.commit()
    factory = async_sessionmaker(
        db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        agent_task_executor,
        "async_session_factory",
        factory,
    )

    class ExecutorFakeGenerator:
        async def generate(self, **_kwargs):
            return "We have received your message and are checking it."

    from app.services import customer_reply_worker

    monkeypatch.setattr(
        customer_reply_worker,
        "DeepSeekCustomerReplyGenerator",
        ExecutorFakeGenerator,
    )
    await agent_task_executor.execute_agent_task(task.id)

    async with factory() as db:
        refreshed_task = await db.get(AgentTask, task.id)
        drafts = (
            await db.execute(
                select(ReplyDraft).where(
                    ReplyDraft.workspace_id == workspace.id
                )
            )
        ).scalars().all()
        run = (
            await db.execute(
                select(ActionRun).where(
                    ActionRun.workspace_id == workspace.id
                )
            )
        ).scalar_one()
        refreshed_item = await db.get(WorkItem, item.id)

    assert refreshed_task.status == "succeeded"
    assert refreshed_task.cost == 0
    assert len(drafts) == 1
    assert run.action_id == "messages.reply"
    assert refreshed_item.requires_action == "confirm"
