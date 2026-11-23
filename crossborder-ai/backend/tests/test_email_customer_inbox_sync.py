"""邮件客服收件同步测试。"""

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.customer_channel import CustomerChannel, CustomerMessage, CustomerThread
from app.models.agent_work import WorkItem
from app.models.user import User
from app.services.email_channel_service import InboundEmail, sync_customer_inbox
from app.services.workspaces import ensure_personal_workspace


class FakeReader:
    def __init__(self, messages):
        self.messages = messages

    async def fetch_inbox(self, *, credentials):
        return self.messages


async def _channel(db_session, email: str):
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
    return workspace, channel


@pytest.mark.asyncio
async def test_inbox_sync_deduplicates_message_and_creates_work_item(db_session):
    workspace, channel = await _channel(
        db_session,
        "inbox-sync@example.com",
    )
    message = InboundEmail(
        message_id="<inbound-1@example.com>",
        thread_id="<inbound-1@example.com>",
        from_email="buyer@example.com",
        subject="Where is my order?",
        body_text="Could you tell me when my parcel will arrive?",
    )
    reader = FakeReader([message])

    first = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=reader,
    )
    second = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=reader,
    )

    assert first["messages_created"] == 1
    assert second["messages_created"] == 0
    assert second["duplicates_skipped"] == 1
    messages = (
        await db_session.execute(
            select(CustomerMessage).where(
                CustomerMessage.workspace_id == workspace.id,
                CustomerMessage.external_message_id == message.message_id,
            )
        )
    ).scalars().all()
    assert len(messages) == 1
    thread = (
        await db_session.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == workspace.id,
                CustomerThread.external_thread_id == message.thread_id,
            )
        )
    ).scalar_one()
    assert thread.customer_email_hash
    assert thread.customer_address_ciphertext
    assert "buyer@example.com" not in thread.customer_address_ciphertext
    work_items = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace.id,
                WorkItem.source_type == "customer_thread",
                WorkItem.source_id == str(thread.id),
            )
        )
    ).scalars().all()
    assert len(work_items) == 1
    assert work_items[0].kind == "customer_reply"
    assert work_items[0].title == "Where is my order?"
