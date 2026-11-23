"""客服意图、风险分流与人工接管测试。"""

import json

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_work import WorkItem
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
)
from app.models.notification import NotificationOutbox
from app.models.user import User
from app.services.customer_intent import classify_customer_message
from app.services.email_channel_service import InboundEmail, sync_customer_inbox
from app.services.workspaces import ensure_personal_workspace


class FakeReader:
    def __init__(self, messages):
        self.messages = messages

    async def fetch_inbox(self, *, credentials):
        return self.messages


async def _workspace_and_channel(db_session, email: str):
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
    await db_session.commit()
    await db_session.refresh(channel)
    return user, workspace, channel


def test_customer_risk_classifier_separates_standard_and_high_risk_messages():
    shipping = classify_customer_message(
        "Could you tell me when my parcel will arrive?"
    )
    refund = classify_customer_message(
        "I want a refund because the product is broken."
    )
    legal = classify_customer_message(
        "I will contact my lawyer and file a chargeback."
    )
    spam = classify_customer_message(
        "Unsubscribe me from this promotional list."
    )
    review = classify_customer_message(
        "The zipper broke after one use.",
        is_review=True,
        rating=2,
    )

    assert shipping.intent == "shipping"
    assert shipping.risk_level == "low"
    assert shipping.auto_reply_candidate is True
    assert refund.intent == "refund_request"
    assert refund.risk_level == "medium"
    assert legal.risk_level == "high"
    assert legal.requires_human is True
    assert spam.intent == "spam"
    assert review.intent == "review_response"
    assert review.risk_level == "medium"


@pytest.mark.asyncio
async def test_high_risk_email_stops_agent_and_creates_takeover_task(db_session):
    user, workspace, channel = await _workspace_and_channel(
        db_session,
        "risk-email@example.com",
    )
    inbound = InboundEmail(
        message_id="<legal-1@example.com>",
        thread_id="<legal-1@example.com>",
        from_email="buyer@example.com",
        subject="Chargeback warning",
        body_text="I will contact my lawyer and file a chargeback today.",
    )

    summary = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([inbound]),
    )
    await db_session.commit()

    thread = (
        await db_session.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    work_item = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace.id,
                WorkItem.source_id == str(thread.id),
            )
        )
    ).scalar_one()
    notification = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.workspace_id == workspace.id,
                NotificationOutbox.user_id == user.id,
            )
        )
    ).scalar_one()
    result = json.loads(work_item.result_json)

    assert summary["work_items_created"] == 1
    assert thread.priority == "urgent"
    assert thread.status == "waiting_user"
    assert work_item.status == "waiting_user"
    assert work_item.requires_action == "none"
    assert work_item.priority == "urgent"
    assert result["intent"] == "complaint"
    assert result["risk_level"] == "high"
    assert result["requires_human"] is True
    assert notification.notification_type == "needs_action"


@pytest.mark.asyncio
async def test_spam_email_is_stored_without_creating_agent_work(db_session):
    _user, workspace, channel = await _workspace_and_channel(
        db_session,
        "risk-spam@example.com",
    )
    inbound = InboundEmail(
        message_id="<spam-1@example.com>",
        thread_id="<spam-1@example.com>",
        from_email="bulk@example.com",
        subject="SEO promotion",
        body_text="Unsubscribe me from this promotional list.",
    )

    summary = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([inbound]),
    )
    await db_session.commit()

    thread = (
        await db_session.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    work_items = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalars().all()

    assert summary["messages_created"] == 1
    assert summary["work_items_created"] == 0
    assert thread.status == "resolved"
    assert work_items == []


@pytest.mark.asyncio
async def test_existing_thread_escalates_when_customer_adds_legal_threat(
    db_session,
):
    user, workspace, channel = await _workspace_and_channel(
        db_session,
        "risk-escalation@example.com",
    )
    first = InboundEmail(
        message_id="<thread-shipping@example.com>",
        thread_id="<thread-1@example.com>",
        from_email="buyer@example.com",
        subject="Where is my parcel?",
        body_text="Could you tell me when my parcel will arrive?",
    )
    await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([first]),
    )
    await db_session.commit()
    thread = (
        await db_session.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == workspace.id
            )
        )
    ).scalar_one()

    second = InboundEmail(
        message_id="<thread-legal@example.com>",
        thread_id="<thread-1@example.com>",
        from_email="buyer@example.com",
        subject="Re: Where is my parcel?",
        body_text="If this is not resolved, I will contact my lawyer.",
    )
    await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([second]),
    )
    await db_session.commit()

    await db_session.refresh(thread)
    item = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace.id,
                WorkItem.source_id == str(thread.id),
            )
        )
    ).scalar_one()
    result = json.loads(item.result_json)
    notifications = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.workspace_id == workspace.id,
                NotificationOutbox.user_id == user.id,
            )
        )
    ).scalars().all()

    assert thread.priority == "urgent"
    assert thread.status == "waiting_user"
    assert item.priority == "urgent"
    assert item.status == "waiting_user"
    assert item.requires_action == "none"
    assert result["risk_level"] == "high"
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_operator_can_take_over_high_risk_customer_thread(
    client,
    db_session,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "risk-takeover@example.com",
            "username": "risk-takeover",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "risk-takeover@example.com")
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
        external_thread_id="takeover-thread",
        thread_type="direct_message",
        subject="Legal complaint",
        language="en",
        status="waiting_user",
        priority="urgent",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        CustomerMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            external_message_id="<takeover-inbound@example.com>",
            direction="inbound",
            body_text="I will contact my lawyer and file a chargeback.",
            send_status="received",
        )
    )
    item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="高风险客户消息",
        summary="需要人工接管",
        status="waiting_user",
        priority="urgent",
        requires_action="none",
        current_step="等待你接管",
        source_type="customer_thread",
        source_id=str(thread.id),
    )
    db_session.add(item)
    await db_session.commit()

    takeover = await client.post(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/customer-threads/{thread.id}/takeover"
        ),
        headers=headers,
    )
    detail = await client.get(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/work-items/{item.id}"
        ),
        headers=headers,
    )

    assert takeover.status_code == 200
    assert takeover.json()["assigned_to_me"] is True
    assert detail.status_code == 200
    customer_context = detail.json()["customer_context"]
    assert customer_context["intent"] == "complaint"
    assert customer_context["risk_level"] == "high"
    assert customer_context["requires_human"] is True
    assert customer_context["assigned_to_me"] is True
    await db_session.refresh(thread)
    await db_session.refresh(item)
    assert thread.assigned_user_id == user.id
    assert item.assignee_user_id == user.id
    assert item.requires_action == "none"
    assert "接管" in item.current_step
