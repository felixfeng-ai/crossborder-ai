"""邮件附件私有存储与退信状态对账测试。"""

import hashlib

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.customer_channel import (
    CustomerAttachment,
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
)
from app.models.agent_work import WorkItem
from app.models.user import User
from app.core.config import settings
from app.services.email_channel_service import (
    InboundAttachment,
    InboundEmail,
    parse_inbound_email,
    sync_customer_inbox,
)
from app.services.workspaces import ensure_personal_workspace


class FakeReader:
    def __init__(self, messages):
        self.messages = messages

    async def fetch_inbox(self, *, credentials):
        return self.messages


class FakeAttachmentStorage:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    async def put_bytes(self, key, data, *, content_type):
        self.objects[key] = (data, content_type)

    async def get_bytes(self, key):
        return self.objects[key][0]

    async def delete(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)


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
    return user, workspace, channel


def test_email_parser_extracts_safe_attachments_and_ignores_executables():
    raw = (
        b"From: Buyer <buyer@example.com>\r\n"
        b"To: support@example.com\r\n"
        b"Subject: Damaged item\r\n"
        b"Message-ID: <attachment-1@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=boundary-1\r\n"
        b"\r\n"
        b"--boundary-1\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"The attached photo shows the damage.\r\n"
        b"--boundary-1\r\n"
        b"Content-Type: image/jpeg; name=damage.jpg\r\n"
        b"Content-Disposition: attachment; filename=damage.jpg\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"/9j/2Q==\r\n"
        b"--boundary-1\r\n"
        b"Content-Type: application/x-msdownload; name=install.exe\r\n"
        b"Content-Disposition: attachment; filename=install.exe\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"TVqQAAMAAAAEAAAA\r\n"
        b"--boundary-1--\r\n"
    )

    parsed = parse_inbound_email(raw)

    assert parsed is not None
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].file_name == "damage.jpg"
    assert parsed.attachments[0].content_type == "image/jpeg"
    assert parsed.attachments[0].data.startswith(b"\xff\xd8")


@pytest.mark.asyncio
async def test_inbound_attachment_is_private_stored_and_deduplicated(db_session):
    _user, workspace, channel = await _channel(
        db_session,
        "attachment-sync@example.com",
    )
    inbound = InboundEmail(
        message_id="<attachment-sync@example.com>",
        thread_id="<attachment-sync@example.com>",
        from_email="buyer@example.com",
        subject="Damaged item",
        body_text="Please see the attached photo.",
        attachments=[
            InboundAttachment(
                file_name="damage.jpg",
                content_type="image/jpeg",
                data=b"\xff\xd8\xff\xe0fake-jpeg",
            )
        ],
    )
    storage = FakeAttachmentStorage()

    first = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([inbound]),
        attachment_storage=storage,
    )
    await db_session.commit()
    second = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([inbound]),
        attachment_storage=storage,
    )
    await db_session.commit()

    attachments = (
        await db_session.execute(
            select(CustomerAttachment).where(
                CustomerAttachment.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    assert first["attachments_created"] == 1
    assert second["duplicates_skipped"] == 1
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment.file_name == "damage.jpg"
    assert attachment.content_type == "image/jpeg"
    assert attachment.checksum_sha256 == hashlib.sha256(
        inbound.attachments[0].data
    ).hexdigest()
    assert storage.objects[attachment.storage_key][0] == (
        inbound.attachments[0].data
    )
    assert "buyer@example.com" not in attachment.storage_key


@pytest.mark.asyncio
async def test_bounce_reconciliation_marks_original_outbound_as_bounced(
    db_session,
):
    _user, workspace, channel = await _channel(
        db_session,
        "bounce-sync@example.com",
    )
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="bounce-thread",
        thread_type="direct_message",
        customer_address_ciphertext=encrypt_value("buyer@example.com"),
        subject="Order update",
        language="en",
        status="waiting_customer",
    )
    db_session.add(thread)
    await db_session.flush()
    outbound = CustomerMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        external_message_id="<sent-1@example.com>",
        direction="outbound",
        body_text="Your order has shipped.",
        send_status="sent",
        idempotency_key="sent-1",
    )
    db_session.add(outbound)
    await db_session.commit()
    bounce = InboundEmail(
        message_id="<bounce-1@example.com>",
        thread_id="<sent-1@example.com>",
        from_email="mailer-daemon@example.com",
        subject="Undeliverable: Order update",
        body_text="Delivery failed.",
        is_bounce=True,
        failed_recipient="buyer@example.com",
        diagnostic="550 mailbox unavailable",
    )

    summary = await sync_customer_inbox(
        db_session,
        channel=channel,
        reader=FakeReader([bounce]),
        attachment_storage=FakeAttachmentStorage(),
    )
    await db_session.commit()

    await db_session.refresh(outbound)
    messages = (
        await db_session.execute(
            select(CustomerMessage).where(
                CustomerMessage.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    assert summary["bounces_reconciled"] == 1
    assert outbound.send_status == "bounced"
    assert outbound.delivery_error_code == "550"
    assert "mailbox unavailable" in outbound.delivery_error_message
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_attachment_summary_and_file_are_workspace_private(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "attachment-api@example.com",
            "username": "attachment-api",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "attachment-api@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path))
    storage_key = "customer-attachments/workspace/thread/message/file"
    target = tmp_path / storage_key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xd8\xff\xe0api-attachment")
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
        external_thread_id="attachment-api-thread",
        thread_type="direct_message",
        subject="Photo attached",
        language="en",
    )
    db_session.add(thread)
    await db_session.flush()
    message = CustomerMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        external_message_id="<attachment-api@example.com>",
        direction="inbound",
        body_text="Please see the attachment.",
        send_status="received",
    )
    db_session.add(message)
    await db_session.flush()
    attachment = CustomerAttachment(
        workspace_id=workspace.id,
        thread_id=thread.id,
        message_id=message.id,
        file_name="photo.jpg",
        content_type="image/jpeg",
        file_size=target.stat().st_size,
        checksum_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        storage_key=storage_key,
    )
    db_session.add(attachment)
    item = WorkItem(
        workspace_id=workspace.id,
        kind="customer_reply",
        source="integration",
        title="客户发来图片",
        summary="请查看附件",
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
    file_response = await client.get(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/customer-attachments/{attachment.id}/file"
        ),
        headers=headers,
    )

    assert detail.status_code == 200
    summaries = detail.json()["customer_context"]["attachments"]
    assert summaries == [
        {
            "id": str(attachment.id),
            "file_name": "photo.jpg",
            "content_type": "image/jpeg",
            "file_size": target.stat().st_size,
            "url": (
                f"/api/mobile/v1/workspaces/{workspace.id}"
                f"/customer-attachments/{attachment.id}/file"
            ),
        }
    ]
    assert file_response.status_code == 200
    assert file_response.content == b"\xff\xd8\xff\xe0api-attachment"
