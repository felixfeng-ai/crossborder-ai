"""IMAP 邮件收件同步与客户线程归一化。"""

import hashlib
import imaplib
import json
import re
import uuid
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import default
from email.utils import parseaddr
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.crypto import decrypt_value, encrypt_value
from app.models.customer_channel import (
    CustomerAttachment,
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
)
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.customer_channel import ReplyDraft
from app.models.workspace import Workspace
from app.services.customer_intent import classify_customer_message
from app.services.work_items import create_work_item
from app.services.language_service import detect_language
from app.services.notifications import create_notification
from app.services.audio_storage import (
    AudioObjectStorage,
    get_audio_storage,
)


@dataclass
class InboundEmail:
    """邮件渠道归一化后的入站消息。"""

    message_id: str
    thread_id: str
    from_email: str
    subject: str
    body_text: str
    in_reply_to: str | None = None
    attachments: list["InboundAttachment"] = field(default_factory=list)
    is_bounce: bool = False
    failed_recipient: str | None = None
    diagnostic: str | None = None


@dataclass(frozen=True)
class InboundAttachment:
    """通过安全检查后的邮件附件字节。"""

    file_name: str
    content_type: str
    data: bytes


MAX_EMAIL_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024
SAFE_ATTACHMENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
    "text/plain",
    "text/csv",
}
UNSAFE_ATTACHMENT_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".js",
    ".msi",
    ".ps1",
    ".scr",
    ".vbs",
}


def _safe_attachment(
    *,
    file_name: str,
    content_type: str,
    data: bytes,
) -> InboundAttachment | None:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    safe_name = (
        str(file_name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    )
    if not safe_name or "\x00" in safe_name:
        return None
    suffix = "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if suffix in UNSAFE_ATTACHMENT_EXTENSIONS:
        return None
    if normalized_type not in SAFE_ATTACHMENT_TYPES:
        return None
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        return None
    return InboundAttachment(
        file_name=safe_name[:255],
        content_type=normalized_type,
        data=data,
    )


def _extract_attachments(parsed) -> list[InboundAttachment]:
    attachments: list[InboundAttachment] = []
    total_size = 0
    try:
        candidates = parsed.iter_attachments()
    except Exception:
        return attachments
    for part in candidates:
        if len(attachments) >= MAX_EMAIL_ATTACHMENTS:
            break
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            continue
        attachment = _safe_attachment(
            file_name=str(part.get_filename() or ""),
            content_type=str(part.get_content_type() or ""),
            data=data,
        )
        if attachment is None:
            continue
        if total_size + len(attachment.data) > MAX_TOTAL_ATTACHMENT_BYTES:
            break
        attachments.append(attachment)
        total_size += len(attachment.data)
    return attachments


def _plain_body(parsed) -> str:
    try:
        part = parsed.get_body(preferencelist=("plain",))
        if part is not None:
            return str(part.get_content() or "").strip()
    except Exception:
        return ""
    return ""


def _is_bounce_email(*, from_email: str, subject: str, parsed) -> bool:
    content_type = str(parsed.get_content_type() or "").lower()
    local_part = from_email.split("@", 1)[0].lower()
    lowered = subject.lower()
    return (
        content_type == "multipart/report"
        or local_part in {"mailer-daemon", "postmaster"}
        or any(
            marker in lowered
            for marker in (
                "undeliverable",
                "delivery status notification",
                "delivery failed",
                "mail delivery failed",
                "退信",
                "投递失败",
            )
        )
    )


def _failed_recipient(parsed, body_text: str) -> str | None:
    headers = (
        "X-Failed-Recipients",
        "Final-Recipient",
        "Original-Recipient",
    )
    for header in headers:
        value = parseaddr(str(parsed.get(header) or ""))[1]
        if value:
            return value.lower()
        match = re.search(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            str(parsed.get(header) or ""),
        )
        if match:
            return match.group(0).lower()
    match = re.search(
        r"(?:final-recipient|original-recipient|failed recipient)"
        r"[^\w.+-]*[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        body_text,
        flags=re.IGNORECASE,
    )
    if match:
        address = re.search(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            match.group(0),
        )
        if address:
            return address.group(0).lower()
    return None


def parse_inbound_email(
    raw: bytes,
    *,
    fallback_id: str | None = None,
) -> InboundEmail | None:
    """把原始 MIME 邮件解析为安全、可测试的领域对象。"""

    parsed = message_from_bytes(raw, policy=default)
    from_email = parseaddr(parsed.get("From", ""))[1].strip().lower()
    subject = str(parsed.get("Subject") or "").strip()
    message_id = (
        str(parsed.get("Message-ID") or "").strip()
        or fallback_id
        or ""
    )
    if not message_id:
        return None
    in_reply_to = str(parsed.get("In-Reply-To") or "").strip() or None
    body_text = _plain_body(parsed)
    is_bounce = _is_bounce_email(
        from_email=from_email,
        subject=subject,
        parsed=parsed,
    )
    return InboundEmail(
        message_id=message_id,
        thread_id=in_reply_to or message_id,
        from_email=from_email,
        subject=subject,
        body_text=body_text,
        in_reply_to=in_reply_to,
        attachments=[] if is_bounce else _extract_attachments(parsed),
        is_bounce=is_bounce,
        failed_recipient=(
            _failed_recipient(parsed, body_text) if is_bounce else None
        ),
        diagnostic=body_text[:1000] if is_bounce else None,
    )


class EmailReader(Protocol):
    async def fetch_inbox(self, *, credentials: dict) -> list[InboundEmail]:
        """读取收件箱；实现方负责连接、认证和消息解析。"""


class IMAPEmailReader:
    """使用工作区 IMAP 配置读取收件箱。"""

    async def fetch_inbox(self, *, credentials: dict) -> list[InboundEmail]:
        return await run_in_threadpool(self._fetch_inbox_sync, credentials)

    @staticmethod
    def _fetch_inbox_sync(credentials: dict) -> list[InboundEmail]:
        host = str(credentials.get("imap_host") or "").strip()
        if not host:
            raise ValueError("邮件渠道未配置 IMAP 主机")
        port = int(credentials.get("imap_port") or 993)
        username = str(credentials.get("imap_username") or "").strip()
        password = str(credentials.get("imap_password") or "")
        folder = str(credentials.get("imap_folder") or "INBOX")
        security = str(credentials.get("imap_security") or "ssl").lower()
        if security == "ssl":
            client = imaplib.IMAP4_SSL(host, port)
        else:
            client = imaplib.IMAP4(host, port)
            if security == "starttls":
                client.starttls()
                client.login(username, password)
        if security == "ssl":
            client.login(username, password)
        try:
            status, _ = client.select(folder)
            if status != "OK":
                raise ValueError("无法打开客服邮箱收件箱")
            status, data = client.search(None, "UNSEEN")
            if status != "OK":
                return []
            messages: list[InboundEmail] = []
            for sequence in data[0].split()[-20:]:
                fetch_status, parts = client.fetch(sequence, "(RFC822)")
                if fetch_status != "OK":
                    continue
                raw = next(
                    (
                        part[1]
                        for part in parts
                        if isinstance(part, tuple) and len(part) >= 2
                    ),
                    None,
                )
                if not raw:
                    continue
                parsed_message = parse_inbound_email(
                    raw,
                    fallback_id=(
                        f"<imap-{sequence.decode(errors='ignore')}@local>"
                    ),
                )
                if parsed_message is not None:
                    messages.append(parsed_message)
            return messages
        finally:
            try:
                client.logout()
            except Exception:
                pass


def _email_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


async def _notify_high_risk_customer(
    db: AsyncSession,
    *,
    channel: CustomerChannel,
    thread: CustomerThread,
    work_item_id,
) -> None:
    workspace = await db.get(Workspace, channel.workspace_id)
    notify_user_id = (
        channel.created_by_user_id
        or (workspace.owner_user_id if workspace else None)
    )
    if notify_user_id is None:
        return
    await create_notification(
        db,
        workspace_id=channel.workspace_id,
        user_id=notify_user_id,
        work_item_id=work_item_id,
        notification_type="needs_action",
        title="有一条高风险客户消息",
        body="请接管后再决定如何回复。",
        deep_link=(
            f"/t/{work_item_id}?workspaceId={channel.workspace_id}"
        ),
        dedupe_key=f"customer-thread:{thread.id}:risk",
    )


def _delivery_error_code(diagnostic: str | None) -> str:
    match = re.search(r"\b([245]\d{2})\b", diagnostic or "")
    return match.group(1) if match else "bounce"


async def _reconcile_email_bounce(
    db: AsyncSession,
    *,
    channel: CustomerChannel,
    inbound: InboundEmail,
) -> bool:
    """把退信对账到原始外发消息，绝不把 SMTP 受理当作已送达。"""

    candidate_ids = {
        value
        for value in (inbound.in_reply_to, inbound.thread_id)
        if value
    }
    outbound = None
    if candidate_ids:
        outbound = (
            await db.execute(
                select(CustomerMessage).where(
                    CustomerMessage.workspace_id == channel.workspace_id,
                    CustomerMessage.direction == "outbound",
                    CustomerMessage.external_message_id.in_(candidate_ids),
                )
            )
        ).scalars().first()
    if outbound is None and inbound.failed_recipient:
        recent = (
            await db.execute(
                select(CustomerMessage, CustomerThread)
                .join(
                    CustomerThread,
                    CustomerMessage.thread_id == CustomerThread.id,
                )
                .where(
                    CustomerMessage.workspace_id == channel.workspace_id,
                    CustomerMessage.direction == "outbound",
                    CustomerThread.customer_address_ciphertext.is_not(None),
                )
                .order_by(CustomerMessage.created_at.desc())
                .limit(100)
            )
        ).all()
        for message, thread in recent:
            try:
                recipient = decrypt_value(
                    thread.customer_address_ciphertext
                )
            except Exception:
                continue
            if recipient.strip().lower() == inbound.failed_recipient.lower():
                outbound = message
                break
    if outbound is None:
        return False

    diagnostic = inbound.diagnostic or inbound.body_text
    outbound.send_status = "bounced"
    outbound.delivery_error_code = _delivery_error_code(diagnostic)
    outbound.delivery_error_message = diagnostic[:2000]
    latest_draft = (
        await db.execute(
            select(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == channel.workspace_id,
                ReplyDraft.thread_id == outbound.thread_id,
            )
            .order_by(ReplyDraft.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_draft is not None and latest_draft.status == "sent":
        latest_draft.status = "failed"

    existing_item = (
        await db.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == channel.workspace_id,
                WorkItem.source_type == "customer_message",
                WorkItem.source_id == str(outbound.id),
            )
        )
    ).scalar_one_or_none()
    if existing_item is None:
        item = await create_work_item(
            db,
            workspace_id=channel.workspace_id,
            actor_user_id=channel.created_by_user_id,
            kind="customer_reply",
            source="integration",
            title="客户回复没有送达",
            summary="邮件服务返回退信，Agent 需要改用其他方式联系买家。",
            priority="urgent",
            status="waiting_user",
            requires_action="none",
            current_step="检查客户邮箱或改用其他联系渠道",
            source_type="customer_message",
            source_id=str(outbound.id),
            channel_type="email",
            channel_id=str(channel.id),
            result={
                "delivery_status": "bounced",
                "error_code": outbound.delivery_error_code,
            },
        )
        workspace = await db.get(Workspace, channel.workspace_id)
        notify_user_id = (
            channel.created_by_user_id
            or (workspace.owner_user_id if workspace else None)
        )
        if notify_user_id is not None:
            await create_notification(
                db,
                workspace_id=channel.workspace_id,
                user_id=notify_user_id,
                work_item_id=item.id,
                notification_type="needs_action",
                title="客户回复没有送达",
                body="邮件服务返回退信，请检查联系方式。",
                deep_link=(
                    f"/t/{item.id}?workspaceId={channel.workspace_id}"
                ),
                dedupe_key=f"customer-message:{outbound.id}:bounce",
            )
    return True


async def sync_customer_inbox(
    db: AsyncSession,
    *,
    channel: CustomerChannel,
    reader: EmailReader | None = None,
    attachment_storage: AudioObjectStorage | None = None,
) -> dict:
    """把收件箱消息归一化入库，并以外部 Message-ID 去重。"""

    credentials = json.loads(
        decrypt_value(channel.credentials_ciphertext)
    )
    messages = await (reader or IMAPEmailReader()).fetch_inbox(
        credentials=credentials
    )
    attachment_store = attachment_storage or get_audio_storage()
    created = 0
    duplicates = 0
    work_items_created = 0
    attachments_created = 0
    bounces_reconciled = 0
    bounces_unmatched = 0

    for inbound in messages:
        if inbound.is_bounce:
            if await _reconcile_email_bounce(
                db,
                channel=channel,
                inbound=inbound,
            ):
                bounces_reconciled += 1
            else:
                bounces_unmatched += 1
            continue
        language = detect_language(inbound.body_text)
        assessment = classify_customer_message(inbound.body_text)
        existing = (
            await db.execute(
                select(CustomerMessage).where(
                    CustomerMessage.workspace_id == channel.workspace_id,
                    CustomerMessage.external_message_id == inbound.message_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            duplicates += 1
            continue

        thread = (
            await db.execute(
                select(CustomerThread).where(
                    CustomerThread.workspace_id == channel.workspace_id,
                    CustomerThread.channel_id == channel.id,
                    CustomerThread.external_thread_id == inbound.thread_id,
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            thread = CustomerThread(
                workspace_id=channel.workspace_id,
                channel_id=channel.id,
                external_thread_id=inbound.thread_id,
                thread_type="direct_message",
                customer_ref=inbound.from_email,
                customer_email_hash=_email_hash(inbound.from_email),
                customer_address_ciphertext=encrypt_value(inbound.from_email),
                subject=inbound.subject or None,
                language=language,
                status=(
                    "resolved"
                    if assessment.intent == "spam"
                    else "waiting_user"
                ),
                priority=assessment.priority,
            )
            db.add(thread)
            await db.flush()
            if assessment.intent != "spam":
                work_item = await create_work_item(
                    db,
                    workspace_id=channel.workspace_id,
                    actor_user_id=channel.created_by_user_id,
                    kind="customer_reply",
                    source="integration",
                    title=inbound.subject or "客户发来一条新消息",
                    summary=(
                        "客户消息涉及高风险内容，Agent 已停止自动回复。"
                        if assessment.requires_human
                        else "客户新消息已同步，Agent 正在准备回复。"
                    ),
                    priority=assessment.priority,
                    status=(
                        "waiting_user"
                        if assessment.requires_human
                        else "running"
                    ),
                    requires_action="none",
                    current_step=(
                        "需要人工接管后再决定如何回复"
                        if assessment.requires_human
                        else "Agent 正在读取客户消息"
                    ),
                    source_type="customer_thread",
                    source_id=str(thread.id),
                    channel_type="email",
                    channel_id=str(channel.id),
                    result=assessment.to_dict(),
                )
                work_items_created += 1
                if assessment.requires_human:
                    await _notify_high_risk_customer(
                        db,
                        channel=channel,
                        thread=thread,
                        work_item_id=work_item.id,
                    )
        else:
            thread.unread_count += 1
            thread.subject = thread.subject or inbound.subject or None
            thread.priority = assessment.priority
            if assessment.requires_human:
                thread.status = "waiting_user"
                work_item = (
                    await db.execute(
                        select(WorkItem)
                        .where(
                            WorkItem.workspace_id == channel.workspace_id,
                            WorkItem.source_type == "customer_thread",
                            WorkItem.source_id == str(thread.id),
                        )
                        .order_by(WorkItem.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if work_item is None:
                    work_item = await create_work_item(
                        db,
                        workspace_id=channel.workspace_id,
                        actor_user_id=channel.created_by_user_id,
                        kind="customer_reply",
                        source="integration",
                        title=inbound.subject or "高风险客户消息",
                        summary="客户消息风险升级，Agent 已停止自动回复。",
                        priority="urgent",
                        status="waiting_user",
                        requires_action="none",
                        current_step="需要人工接管后再决定如何回复",
                        source_type="customer_thread",
                        source_id=str(thread.id),
                        channel_type="email",
                        channel_id=str(channel.id),
                        result=assessment.to_dict(),
                    )
                    work_items_created += 1
                else:
                    try:
                        result = json.loads(work_item.result_json or "{}")
                    except json.JSONDecodeError:
                        result = {}
                    result.update(assessment.to_dict())
                    work_item.priority = "urgent"
                    work_item.status = "waiting_user"
                    work_item.requires_action = "none"
                    work_item.current_step = "客户风险升级，需要人工接管"
                    work_item.result_json = json.dumps(
                        result,
                        ensure_ascii=False,
                    )
                    work_item.version += 1
                    db.add(
                        WorkItemEvent(
                            workspace_id=channel.workspace_id,
                            work_item_id=work_item.id,
                            event_type="customer_thread.risk_escalated",
                            actor_user_id=channel.created_by_user_id,
                            payload_json=json.dumps(
                                {
                                    "thread_id": str(thread.id),
                                    "risk_level": assessment.risk_level,
                                    "intent": assessment.intent,
                                },
                                ensure_ascii=False,
                            ),
                        )
                    )
                await _notify_high_risk_customer(
                    db,
                    channel=channel,
                    thread=thread,
                    work_item_id=work_item.id,
                )

        message = CustomerMessage(
            workspace_id=channel.workspace_id,
            thread_id=thread.id,
            external_message_id=inbound.message_id,
            direction="inbound",
            body_text=inbound.body_text,
            language=language,
            send_status="received",
        )
        db.add(message)
        await db.flush()
        attachment_ids: list[str] = []
        stored_keys: list[str] = []
        try:
            for attachment in inbound.attachments:
                attachment_id = uuid.uuid4()
                storage_key = (
                    f"customer-attachments/{channel.workspace_id}/"
                    f"{thread.id}/{message.id}/{attachment_id}"
                )
                await attachment_store.put_bytes(
                    storage_key,
                    attachment.data,
                    content_type=attachment.content_type,
                )
                stored_keys.append(storage_key)
                db.add(
                    CustomerAttachment(
                        id=attachment_id,
                        workspace_id=channel.workspace_id,
                        thread_id=thread.id,
                        message_id=message.id,
                        file_name=attachment.file_name,
                        content_type=attachment.content_type,
                        file_size=len(attachment.data),
                        checksum_sha256=hashlib.sha256(
                            attachment.data
                        ).hexdigest(),
                        storage_key=storage_key,
                    )
                )
                attachment_ids.append(str(attachment_id))
                attachments_created += 1
            if attachment_ids:
                message.asset_ids_json = json.dumps(attachment_ids)
                await db.flush()
        except Exception:
            for storage_key in stored_keys:
                await attachment_store.delete(storage_key)
            raise
        created += 1
        thread.last_message_at = datetime.now(timezone.utc)

    channel.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "messages_scanned": len(messages),
        "messages_created": created,
        "duplicates_skipped": duplicates,
        "work_items_created": work_items_created,
        "attachments_created": attachments_created,
        "bounces_reconciled": bounces_reconciled,
        "bounces_unmatched": bounces_unmatched,
    }


async def sync_all_customer_inboxes(db: AsyncSession) -> dict:
    """同步所有启用的客户渠道，单渠道失败不影响其他工作区。"""

    channels = (
        await db.execute(
            select(CustomerChannel).where(
                CustomerChannel.provider.in_(["imap_smtp", "judge_me"]),
                CustomerChannel.status == "active",
            )
        )
    ).scalars().all()
    result = {
        "channels_scanned": len(channels),
        "channels_succeeded": 0,
        "channels_failed": 0,
        "messages_created": 0,
        "attachments_created": 0,
        "bounces_reconciled": 0,
        "failures": [],
    }
    for channel in channels:
        try:
            if channel.provider == "judge_me":
                # 延迟导入避免邮件渠道和评价渠道在模块加载时互相依赖。
                from app.services.judge_me_review_service import (
                    sync_judge_me_reviews,
                )

                summary = await sync_judge_me_reviews(
                    db,
                    channel=channel,
                )
            else:
                summary = await sync_customer_inbox(db, channel=channel)
            await db.commit()
            result["channels_succeeded"] += 1
            result["messages_created"] += summary["messages_created"]
            result["attachments_created"] += summary.get(
                "attachments_created",
                0,
            )
            result["bounces_reconciled"] += summary.get(
                "bounces_reconciled",
                0,
            )
        except Exception as exc:
            await db.rollback()
            result["channels_failed"] += 1
            result["failures"].append(
                {
                    "channel_id": str(channel.id),
                    "error": str(exc)[:200],
                }
            )
    return result
