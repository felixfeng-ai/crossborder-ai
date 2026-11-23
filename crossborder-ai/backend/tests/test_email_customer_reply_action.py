"""邮件客服回复动作测试。"""

import json
import smtplib
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
    ReplyDraft,
)
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.services.action_runtime import ActionExecution
from app.services.customer_reply_adapter import (
    CustomerReplyActionAdapter,
    OutboundAttachment,
    SentEmail,
    SMTPEmailSender,
    create_reply_draft,
    create_translated_reply_draft,
)
from app.services.language_service import detect_language
from app.services.workspaces import ensure_personal_workspace
from app.core.config import settings


class FakeEmailSender:
    def __init__(self):
        self.calls = []

    async def send(self, **kwargs):
        self.calls.append(kwargs)
        return SentEmail(
            external_message_id=f"<sent-{len(self.calls)}@example.com>"
        )


class FakeTranslator:
    def __init__(self):
        self.calls = []

    async def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        customer_message: str,
    ) -> str:
        self.calls.append(
            {
                "text": text,
                "source_language": source_language,
                "target_language": target_language,
                "customer_message": customer_message,
            }
        )
        return "Your parcel is expected to arrive within two days."


async def _reply_context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    credentials = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "support@example.com",
        "smtp_password": "secret",
        "smtp_from": "support@example.com",
        "smtp_security": "starttls",
    }
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        provider="imap_smtp",
        external_account_id="support@example.com",
        display_name="客服邮箱",
        credentials_ciphertext=encrypt_value(json.dumps(credentials)),
        status="active",
    )
    db_session.add(channel)
    await db_session.flush()
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="thread-1",
        thread_type="direct_message",
        customer_ref="buyer-1",
        customer_email_hash="hash-buyer",
        customer_address_ciphertext=encrypt_value("buyer@example.com"),
        subject="Where is my order?",
        language="en",
        status="waiting_user",
    )
    db_session.add(thread)
    await db_session.flush()
    draft = ReplyDraft(
        workspace_id=workspace.id,
        thread_id=thread.id,
        version=1,
        language="en",
        body_text="Your parcel is on the way.",
        risk_level="medium",
        status="ready",
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(channel)
    await db_session.refresh(thread)
    await db_session.refresh(draft)
    return user, workspace, channel, thread, draft


@pytest.mark.asyncio
async def test_reply_preflight_validates_thread_and_latest_draft(db_session):
    user, workspace, channel, thread, draft = await _reply_context(
        db_session,
        "reply-preflight@example.com",
    )
    adapter = CustomerReplyActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        sender=FakeEmailSender(),
    )

    snapshot = await adapter.preflight(
        action_id="messages.reply",
        target_id=str(thread.id),
        input_data={
            "channel_id": str(channel.id),
            "thread_id": str(thread.id),
            "draft_id": str(draft.id),
        },
    )

    assert snapshot["thread_id"] == str(thread.id)
    assert snapshot["draft_version"] == 1
    assert snapshot["recipient"] == "buyer@example.com"
    assert snapshot["subject"] == "Re: Where is my order?"


@pytest.mark.asyncio
async def test_reply_sends_once_and_reuses_outbound_message(db_session):
    user, workspace, channel, thread, draft = await _reply_context(
        db_session,
        "reply-send@example.com",
    )
    sender = FakeEmailSender()
    adapter = CustomerReplyActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        sender=sender,
    )
    input_data = {
        "channel_id": str(channel.id),
        "thread_id": str(thread.id),
        "draft_id": str(draft.id),
        "in_reply_to": "<inbound@example.com>",
    }

    execution = await adapter.execute(
        action_id="messages.reply",
        target_id=str(thread.id),
        input_data=input_data,
        idempotency_key="reply-action-1",
    )
    verification = await adapter.verify(
        action_id="messages.reply",
        target_id=str(thread.id),
        execution=execution,
    )
    replay = await adapter.execute(
        action_id="messages.reply",
        target_id=str(thread.id),
        input_data=input_data,
        idempotency_key="reply-action-1",
    )

    assert len(sender.calls) == 1
    assert sender.calls[0]["to_email"] == "buyer@example.com"
    assert sender.calls[0]["subject"] == "Re: Where is my order?"
    assert sender.calls[0]["in_reply_to"] == "<inbound@example.com>"
    assert execution.external_id == "<sent-1@example.com>"
    assert replay.external_id == execution.external_id
    assert replay.output["replayed"] is True
    assert verification.matched is True

    message = (
        await db_session.execute(
            select(CustomerMessage).where(
                CustomerMessage.workspace_id == workspace.id,
                CustomerMessage.thread_id == thread.id,
                CustomerMessage.idempotency_key == "reply-action-1",
            )
        )
    ).scalar_one()
    assert message.send_status == "sent"
    assert message.external_message_id == "<sent-1@example.com>"
    await db_session.refresh(draft)
    assert draft.status == "sent"
    await db_session.refresh(thread)
    assert thread.status == "waiting_customer"


@pytest.mark.asyncio
async def test_reply_attaches_workspace_images_without_exposing_paths(
    db_session,
    tmp_path,
    monkeypatch,
):
    user, workspace, channel, thread, draft = await _reply_context(
        db_session,
        "reply-attachment@example.com",
    )
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    image_path = Path(tmp_path) / "workspace" / "reply.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"\xff\xd8\xff\xe0reply-image")
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=workspace.id,
        name="reply",
        kind="upload",
        storage_key=str(image_path.relative_to(tmp_path)),
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=image_path.stat().st_size,
    )
    db_session.add(asset)
    await db_session.commit()
    sender = FakeEmailSender()
    adapter = CustomerReplyActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        sender=sender,
    )

    execution = await adapter.execute(
        action_id="messages.reply",
        target_id=str(thread.id),
        input_data={
            "channel_id": str(channel.id),
            "thread_id": str(thread.id),
            "draft_id": str(draft.id),
            "attachment_asset_ids": [str(asset.id)],
        },
        idempotency_key="reply-with-attachment",
    )

    attachments = sender.calls[0]["attachments"]
    assert len(attachments) == 1
    assert attachments[0].file_name == "reply.jpg"
    assert attachments[0].content_type == "image/jpeg"
    assert attachments[0].data == b"\xff\xd8\xff\xe0reply-image"
    assert execution.output["attachment_count"] == 1
    assert "reply.jpg" not in json.dumps(execution.output)


def test_smtp_sender_encodes_attachment_into_mime_message(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def send_message(self, message):
            sent_messages.append(message)

        def quit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    receipt = SMTPEmailSender._send_sync(
        {
            "smtp_host": "smtp.example.com",
            "smtp_username": "support@example.com",
            "smtp_password": "secret",
            "smtp_security": "starttls",
        },
        "buyer@example.com",
        "Re: Damaged item",
        "Please see the attached photo.",
        [
            OutboundAttachment(
                file_name="damage.jpg",
                content_type="image/jpeg",
                data=b"\xff\xd8\xff\xe0image",
            )
        ],
        None,
        "smtp-attachment",
    )

    assert receipt.external_message_id.startswith("<")
    attachments = list(sent_messages[0].iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "damage.jpg"
    assert attachments[0].get_content_type() == "image/jpeg"
    assert attachments[0].get_payload(decode=True) == b"\xff\xd8\xff\xe0image"


@pytest.mark.asyncio
async def test_reply_rejects_stale_draft(db_session):
    user, workspace, channel, thread, draft = await _reply_context(
        db_session,
        "reply-stale@example.com",
    )
    newer = await create_reply_draft(
        db_session,
        workspace_id=workspace.id,
        thread_id=thread.id,
        body_text="Updated reply with delivery date.",
        language="en",
    )
    await db_session.commit()
    adapter = CustomerReplyActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        sender=FakeEmailSender(),
    )

    with pytest.raises(ValueError, match="草稿"):
        await adapter.preflight(
            action_id="orders.delay_notice",
            target_id=str(thread.id),
            input_data={
                "channel_id": str(channel.id),
                "thread_id": str(thread.id),
                "draft_id": str(draft.id),
            },
        )
    assert newer.version == 2


@pytest.mark.asyncio
async def test_verify_returns_failed_when_outbound_record_is_missing(db_session):
    user, workspace, _channel, thread, _draft = await _reply_context(
        db_session,
        "reply-missing@example.com",
    )
    adapter = CustomerReplyActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        sender=FakeEmailSender(),
    )

    verification = await adapter.verify(
        action_id="messages.reply",
        target_id=str(thread.id),
        execution=ActionExecution(
            external_id="<missing@example.com>",
            output={"idempotency_key": "missing-action"},
        ),
    )

    assert verification.matched is False
    assert "找不到" in verification.details["error"]


def test_language_detection_handles_chinese_english_and_mixed_text():
    assert detect_language("请帮我回复客户，说明物流延迟。") == "zh"
    assert detect_language("Your order will arrive tomorrow.") == "en"
    assert detect_language("Hola, ¿dónde está mi pedido?") == "es"


@pytest.mark.asyncio
async def test_chinese_seller_instruction_is_translated_to_customer_language(
    db_session,
):
    user, workspace, _channel, thread, _draft = await _reply_context(
        db_session,
        "reply-translate@example.com",
    )
    translator = FakeTranslator()
    draft = await create_translated_reply_draft(
        db_session,
        workspace_id=workspace.id,
        thread_id=thread.id,
        seller_instruction="请告诉客户包裹两天内会到。",
        customer_message="Where is my parcel?",
        translator=translator,
    )
    await db_session.commit()

    assert draft.language == "en"
    assert draft.source_language == "zh"
    assert draft.body_text == "Your parcel is expected to arrive within two days."
    assert translator.calls[0]["target_language"] == "en"
    assert translator.calls[0]["source_language"] == "zh"
    assert translator.calls[0]["customer_message"] == "Where is my parcel?"


@pytest.mark.asyncio
async def test_seller_can_override_translation_target_language(db_session):
    _user, workspace, _channel, thread, _draft = await _reply_context(
        db_session,
        "reply-translate-target@example.com",
    )
    translator = FakeTranslator()
    draft = await create_translated_reply_draft(
        db_session,
        workspace_id=workspace.id,
        thread_id=thread.id,
        seller_instruction="请用德语回复客户。",
        customer_message="Where is my parcel?",
        target_language="de",
        translator=translator,
    )
    await db_session.commit()

    assert draft.language == "de"
    assert translator.calls[0]["target_language"] == "de"
