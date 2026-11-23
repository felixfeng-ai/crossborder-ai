"""邮件客服回复动作适配器。"""

import hashlib
import json
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.crypto import decrypt_value
from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
    ReplyDraft,
)
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.language_service import (
    DeepSeekReplyTranslator,
    ReplyTranslator,
    detect_language,
)


@dataclass
class SentEmail:
    """邮件服务器接受发送后的最小回执。"""

    external_message_id: str


@dataclass(frozen=True)
class OutboundAttachment:
    """只交给邮件发送器的附件字节，不进入动作预览或日志。"""

    file_name: str
    content_type: str
    data: bytes


class EmailSender(Protocol):
    async def send(
        self,
        *,
        credentials: dict,
        to_email: str,
        subject: str,
        body_text: str,
        attachments: list[OutboundAttachment],
        in_reply_to: str | None,
        idempotency_key: str,
    ) -> SentEmail:
        """发送邮件；不得返回未实际提交给邮件服务器的成功。"""


class SMTPEmailSender:
    """用工作区配置的 SMTP 账号发送邮件。"""

    async def send(
        self,
        *,
        credentials: dict,
        to_email: str,
        subject: str,
        body_text: str,
        attachments: list[OutboundAttachment],
        in_reply_to: str | None,
        idempotency_key: str,
    ) -> SentEmail:
        return await run_in_threadpool(
            self._send_sync,
            credentials,
            to_email,
            subject,
            body_text,
            attachments,
            in_reply_to,
            idempotency_key,
        )

    @staticmethod
    def _send_sync(
        credentials: dict,
        to_email: str,
        subject: str,
        body_text: str,
        attachments: list[OutboundAttachment],
        in_reply_to: str | None,
        idempotency_key: str,
    ) -> SentEmail:
        host = str(credentials.get("smtp_host") or "").strip()
        if not host:
            raise ValueError("邮件渠道未配置 SMTP 主机")
        port = int(credentials.get("smtp_port") or 587)
        username = str(credentials.get("smtp_username") or "").strip()
        password = str(credentials.get("smtp_password") or "")
        from_email = str(
            credentials.get("smtp_from") or username
        ).strip()
        security = str(credentials.get("smtp_security") or "starttls").lower()
        if not from_email:
            raise ValueError("邮件渠道未配置发件地址")

        domain = from_email.rsplit("@", 1)[-1]
        digest = hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()[:24]
        message_id = f"<{digest}@veyaship.{domain}>"
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = from_email
        message["To"] = to_email
        message["Message-ID"] = message_id
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to
        message.set_content(body_text)
        for attachment in attachments:
            maintype, _, subtype = attachment.content_type.partition("/")
            message.add_attachment(
                attachment.data,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.file_name,
            )

        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        try:
            server.ehlo()
            if security == "starttls":
                server.starttls()
                server.ehlo()
            if username:
                server.login(username, password)
            server.send_message(message)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()
        return SentEmail(external_message_id=message_id)


async def create_reply_draft(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread_id: UUID,
    body_text: str,
    language: str = "en",
    risk_level: str = "low",
    agent_run_id: UUID | None = None,
    source_language: str | None = None,
) -> ReplyDraft:
    """创建新版本草稿，并把仍在等待的旧版本标记为过期。"""

    latest_version = (
        await db.execute(
            select(func.max(ReplyDraft.version)).where(
                ReplyDraft.workspace_id == workspace_id,
                ReplyDraft.thread_id == thread_id,
            )
        )
    ).scalar() or 0
    old_drafts = (
        await db.execute(
            select(ReplyDraft).where(
                ReplyDraft.workspace_id == workspace_id,
                ReplyDraft.thread_id == thread_id,
                ReplyDraft.status.in_(["ready", "approved", "generating"]),
            )
        )
    ).scalars().all()
    for old in old_drafts:
        old.status = "stale"
    draft = ReplyDraft(
        workspace_id=workspace_id,
        thread_id=thread_id,
        agent_run_id=agent_run_id,
        version=latest_version + 1,
        language=language,
        body_text=body_text.strip(),
        source_language=source_language,
        risk_level=risk_level,
        status="ready",
    )
    db.add(draft)
    await db.flush()
    return draft


async def create_translated_reply_draft(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread_id: UUID,
    seller_instruction: str,
    customer_message: str,
    target_language: str | None = None,
    language: str | None = None,
    translator: ReplyTranslator | None = None,
    risk_level: str = "medium",
    agent_run_id: UUID | None = None,
) -> ReplyDraft:
    """把卖家的中文指令转换成客户语言，再保存为最新版本草稿。"""

    instruction = seller_instruction.strip()
    if not instruction:
        raise ValueError("卖家回复指令不能为空")
    source_language = detect_language(instruction)
    selected_language = (
        target_language
        or language
        or detect_language(customer_message)
        or "en"
    )
    if source_language == selected_language:
        body_text = instruction
    else:
        body_text = await (translator or DeepSeekReplyTranslator()).translate(
            text=instruction,
            source_language=source_language,
            target_language=selected_language,
            customer_message=customer_message,
        )
    if not body_text.strip():
        raise ValueError("翻译服务没有返回可用回复")
    return await create_reply_draft(
        db,
        workspace_id=workspace_id,
        thread_id=thread_id,
        body_text=body_text,
        language=selected_language,
        source_language=source_language,
        risk_level=risk_level,
        agent_run_id=agent_run_id,
    )


class CustomerReplyActionAdapter:
    """发送经过版本确认的客服草稿，并把外部消息编号写回本地。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        user_id: UUID,
        sender: EmailSender | None = None,
    ):
        self.db = db
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.sender = sender or SMTPEmailSender()

    async def _attachments(
        self,
        input_data: dict,
    ) -> list[OutboundAttachment]:
        """只允许当前工作区的私有图片作为外发附件。"""

        raw_ids = input_data.get("attachment_asset_ids") or []
        if not isinstance(raw_ids, list):
            raise ValueError("邮件附件参数格式不正确")
        if len(raw_ids) > 5:
            raise ValueError("单封邮件最多发送 5 张图片")
        if not raw_ids:
            return []
        try:
            asset_ids = [UUID(str(value)) for value in raw_ids]
        except (TypeError, ValueError) as exc:
            raise ValueError("邮件附件编号格式不正确") from exc
        assets = (
            await self.db.execute(
                select(ImageAsset).where(
                    ImageAsset.workspace_id == self.workspace_id,
                    ImageAsset.id.in_(asset_ids),
                    ImageAsset.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        by_id = {asset.id: asset for asset in assets}
        if len(by_id) != len(asset_ids):
            raise ValueError("部分邮件附件不存在或不属于当前工作区")
        root = Path(settings.IMAGE_STORAGE_DIR).resolve()
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        attachments: list[OutboundAttachment] = []
        for asset_id in asset_ids:
            asset = by_id[asset_id]
            if asset.content_type not in extensions:
                raise ValueError("邮件只支持 JPEG、PNG、WebP 或 GIF 图片")
            if asset.file_size > settings.MAX_IMAGE_UPLOAD_BYTES:
                raise ValueError("邮件附件超过大小限制")
            path = (root / asset.storage_key).resolve()
            if path != root and root not in path.parents:
                raise ValueError("邮件附件路径非法")
            if not path.is_file():
                raise ValueError("邮件附件文件不存在")
            suffix = Path(asset.name).suffix.lower()
            file_name = (
                asset.name
                if suffix
                else f"{asset.name}{extensions[asset.content_type]}"
            )
            data = await run_in_threadpool(path.read_bytes)
            attachments.append(
                OutboundAttachment(
                    file_name=file_name[:255],
                    content_type=asset.content_type,
                    data=data,
                )
            )
        return attachments

    async def _context(self, input_data: dict):
        try:
            channel_id = UUID(str(input_data["channel_id"]))
            thread_id = UUID(str(input_data["thread_id"]))
            draft_id = UUID(str(input_data["draft_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("客服回复参数不完整") from exc

        channel = await self.db.get(CustomerChannel, channel_id)
        thread = await self.db.get(CustomerThread, thread_id)
        draft = await self.db.get(ReplyDraft, draft_id)
        if (
            channel is None
            or channel.workspace_id != self.workspace_id
            or channel.status != "active"
        ):
            raise ValueError("客服渠道不存在或已失效")
        if (
            thread is None
            or thread.workspace_id != self.workspace_id
            or thread.channel_id != channel.id
        ):
            raise ValueError("客户会话不存在或不属于当前工作区")
        if (
            draft is None
            or draft.workspace_id != self.workspace_id
            or draft.thread_id != thread.id
        ):
            raise ValueError("回复草稿不存在或与当前会话不匹配")

        latest = (
            await self.db.execute(
                select(ReplyDraft)
                .where(
                    ReplyDraft.workspace_id == self.workspace_id,
                    ReplyDraft.thread_id == thread.id,
                )
                .order_by(ReplyDraft.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None or latest.id != draft.id:
            raise ValueError("回复草稿已过期，请重新生成")
        if draft.status not in {"ready", "approved"}:
            raise ValueError("回复草稿当前不可发送")
        if not draft.body_text.strip():
            raise ValueError("回复正文不能为空")
        if not thread.customer_address_ciphertext:
            raise ValueError("客户会话缺少回信地址")
        recipient = decrypt_value(thread.customer_address_ciphertext)
        credentials = json.loads(
            decrypt_value(channel.credentials_ciphertext)
        )
        subject = str(thread.subject or "").strip() or "Customer reply"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        attachments = await self._attachments(input_data)
        return (
            channel,
            thread,
            draft,
            recipient,
            credentials,
            subject,
            attachments,
        )

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id not in {"messages.reply", "orders.delay_notice"}:
            raise ValueError("适配器不支持该动作")
        (
            channel,
            thread,
            draft,
            recipient,
            _credentials,
            subject,
            attachments,
        ) = await self._context(input_data)
        if str(thread.id) != str(target_id):
            raise ValueError("动作目标会话与输入不一致")
        return {
            "channel_id": str(channel.id),
            "thread_id": str(thread.id),
            "draft_id": str(draft.id),
            "draft_version": draft.version,
            "recipient": recipient,
            "subject": subject,
            "body_text": draft.body_text,
            "attachment_count": len(attachments),
            "in_reply_to": input_data.get("in_reply_to"),
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        existing = (
            await self.db.execute(
                select(CustomerMessage).where(
                    CustomerMessage.workspace_id == self.workspace_id,
                    CustomerMessage.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing_thread = await self.db.get(
                CustomerThread,
                existing.thread_id,
            )
            return ActionExecution(
                external_id=existing.external_message_id,
                output={
                    "idempotency_key": idempotency_key,
                    "thread_id": str(existing.thread_id),
                    "channel_id": (
                        str(existing_thread.channel_id)
                        if existing_thread is not None
                        else None
                    ),
                    "replayed": True,
                },
            )

        snapshot = await self.preflight(
            action_id=action_id,
            target_id=target_id,
            input_data=input_data,
        )
        (
            channel,
            thread,
            draft,
            recipient,
            credentials,
            subject,
            attachments,
        ) = await self._context(input_data)
        outbound = CustomerMessage(
            workspace_id=self.workspace_id,
            thread_id=thread.id,
            direction="outbound",
            body_text=draft.body_text,
            send_status="sending",
            idempotency_key=idempotency_key,
        )
        self.db.add(outbound)
        await self.db.flush()
        # 先落“发送中”记录，进程中断后不会静默重发而不留痕。
        await self.db.commit()

        try:
            sent = await self.sender.send(
                credentials=credentials,
                to_email=recipient,
                subject=subject,
                body_text=draft.body_text,
                attachments=attachments,
                in_reply_to=snapshot.get("in_reply_to"),
                idempotency_key=idempotency_key,
            )
        except Exception:
            outbound.send_status = "failed"
            await self.db.commit()
            raise

        outbound.external_message_id = sent.external_message_id
        outbound.send_status = "sent"
        outbound.sent_at = datetime.now(timezone.utc)
        draft.status = "sent"
        thread.status = "waiting_customer"
        thread.last_message_at = outbound.sent_at
        await self.db.commit()
        return ActionExecution(
            external_id=sent.external_message_id,
            output={
                "idempotency_key": idempotency_key,
                "thread_id": str(thread.id),
                "channel_id": str(channel.id),
                "attachment_count": len(attachments),
                "replayed": False,
            },
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        output = execution.output or {}
        key = str(output.get("idempotency_key") or "")
        if not key:
            return ActionVerification(
                matched=False,
                details={"error": "缺少发送幂等键，无法对账"},
            )
        message = (
            await self.db.execute(
                select(CustomerMessage).where(
                    CustomerMessage.workspace_id == self.workspace_id,
                    CustomerMessage.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if message is None:
            return ActionVerification(
                matched=False,
                details={"error": "回读找不到出站消息"},
            )
        matched = (
            message.send_status == "sent"
            and message.external_message_id == execution.external_id
        )
        return ActionVerification(
            matched=matched,
            snapshot={
                "message_id": str(message.id),
                "external_message_id": message.external_message_id,
                "send_status": message.send_status,
                "sent_at": (
                    message.sent_at.isoformat() if message.sent_at else None
                ),
            },
            details={
                "idempotency_key": key,
                "mismatches": [] if matched else ["send_status"],
            },
        )
