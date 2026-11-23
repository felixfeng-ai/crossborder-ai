"""Judge.me 评价同步与公开回复适配器。"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
    ReplyDraft,
)
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.language_service import detect_language
from app.services.work_items import create_work_item


class JudgeMeAPIError(RuntimeError):
    """Judge.me 返回的业务错误；错误文本不包含访问令牌。"""


def normalize_judge_me_credentials(credentials: dict) -> dict:
    """只保留 Judge.me 服务端调用需要的字段。"""

    api_token = str(credentials.get("api_token") or "").strip()
    shop_domain = str(credentials.get("shop_domain") or "").strip().lower()
    if not api_token:
        raise ValueError("Judge.me 私有 API 令牌不能为空")
    if not shop_domain.endswith(".myshopify.com"):
        raise ValueError("Judge.me 店铺域名必须是 xxx.myshopify.com")
    return {
        "api_token": api_token,
        "shop_domain": shop_domain,
    }


@dataclass(frozen=True)
class JudgeMeReview:
    """归一化后的评价事实，避免上层依赖供应商原始字段。"""

    review_id: str
    body: str
    rating: int
    reviewer_name: str | None = None
    reviewer_email: str | None = None
    review_title: str | None = None
    product_external_id: str | None = None
    product_title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class JudgeMeReplyReceipt:
    """公开回复提交成功后的本地回执。"""

    accepted: bool
    external_id: str | None = None
    response: dict = field(default_factory=dict)


class JudgeMeClient(Protocol):
    """评价渠道的最小能力集合，测试可注入无网络实现。"""

    async def fetch_reviews(
        self,
        *,
        credentials: dict,
        limit: int = 50,
    ) -> list[JudgeMeReview]:
        """读取最近评价。"""

    async def create_public_reply(
        self,
        *,
        credentials: dict,
        review_id: str,
        body_text: str,
        send_reply_email: bool,
        idempotency_key: str,
    ) -> JudgeMeReplyReceipt:
        """发表公开回复；只有 HTTP 成功时才返回 accepted。"""

    async def read_review(
        self,
        *,
        credentials: dict,
        review_id: str,
    ) -> dict:
        """读取单条评价，用于尝试核验公开回复。"""


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _string_id(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_review(payload: dict) -> JudgeMeReview:
    review_id = _string_id(payload.get("id"))
    if not review_id:
        raise JudgeMeAPIError("Judge.me 返回的评价缺少编号")
    try:
        rating = int(payload.get("rating") or 0)
    except (TypeError, ValueError) as exc:
        raise JudgeMeAPIError("Judge.me 返回的评价星级无效") from exc
    reviewer = payload.get("reviewer")
    reviewer_data = reviewer if isinstance(reviewer, dict) else {}
    return JudgeMeReview(
        review_id=review_id,
        body=str(payload.get("body") or "").strip(),
        rating=max(0, min(5, rating)),
        reviewer_name=(
            str(reviewer_data.get("name") or "").strip() or None
        ),
        reviewer_email=(
            str(reviewer_data.get("email") or "").strip().lower() or None
        ),
        review_title=(
            str(payload.get("title") or "").strip() or None
        ),
        product_external_id=_string_id(payload.get("product_external_id")),
        product_title=(
            str(payload.get("product_title") or "").strip() or None
        ),
        created_at=_parse_datetime(payload.get("created_at")),
        updated_at=_parse_datetime(payload.get("updated_at")),
    )


class JudgeMeHTTPClient:
    """通过 Judge.me 私有 API 读取评价并发表公开回复。"""

    BASE_URL = "https://api.judge.me/api/v1"

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.transport = transport

    @staticmethod
    def _credentials(credentials: dict) -> dict:
        try:
            return normalize_judge_me_credentials(credentials)
        except ValueError as exc:
            raise JudgeMeAPIError(str(exc)) from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        credentials: dict,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> Any:
        normalized = self._credentials(credentials)
        request_params = {
            "shop_domain": normalized["shop_domain"],
            **(params or {}),
        }
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=20,
        ) as client:
            response = await client.request(
                method,
                f"{self.BASE_URL}{path}",
                headers={
                    "X-Api-Token": normalized["api_token"],
                    "Content-Type": "application/json",
                },
                params=request_params,
                json=json_data,
            )
        if response.status_code == 429:
            raise JudgeMeAPIError("Judge.me 限流，请稍后重试")
        if response.status_code in {401, 403}:
            raise JudgeMeAPIError("Judge.me 授权已失效")
        if response.status_code >= 400:
            raise JudgeMeAPIError(
                f"Judge.me 请求失败：{response.text[:200]}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise JudgeMeAPIError("Judge.me 返回内容不是有效 JSON") from exc

    async def fetch_reviews(
        self,
        *,
        credentials: dict,
        limit: int = 50,
    ) -> list[JudgeMeReview]:
        payload = await self._request(
            "GET",
            "/reviews",
            credentials=credentials,
            params={
                "page": 1,
                "per_page": max(1, min(100, limit)),
            },
        )
        raw_reviews = (
            payload.get("reviews")
            if isinstance(payload, dict)
            else payload
        )
        if not isinstance(raw_reviews, list):
            return []
        return [
            _normalize_review(item)
            for item in raw_reviews
            if isinstance(item, dict)
        ]

    async def create_public_reply(
        self,
        *,
        credentials: dict,
        review_id: str,
        body_text: str,
        send_reply_email: bool,
        idempotency_key: str,
    ) -> JudgeMeReplyReceipt:
        payload = await self._request(
            "POST",
            "/replies",
            credentials=credentials,
            json_data={
                "review_id": int(review_id),
                "send_reply_email": send_reply_email,
                "reply": {"content": body_text},
            },
        )
        response = payload if isinstance(payload, dict) else {}
        external_id = (
            _string_id(response.get("id"))
            or _string_id(
                (response.get("reply") or {}).get("id")
                if isinstance(response.get("reply"), dict)
                else None
            )
        )
        if not external_id:
            digest = hashlib.sha256(
                idempotency_key.encode("utf-8")
            ).hexdigest()[:24]
            external_id = f"judge-me-reply:{review_id}:{digest}"
        return JudgeMeReplyReceipt(
            accepted=True,
            external_id=external_id,
            response=response,
        )

    async def read_review(
        self,
        *,
        credentials: dict,
        review_id: str,
    ) -> dict:
        payload = await self._request(
            "GET",
            f"/reviews/{review_id}",
            credentials=credentials,
        )
        if not isinstance(payload, dict):
            return {}
        review = payload.get("review")
        return review if isinstance(review, dict) else payload


def _email_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _review_thread_key(review_id: str) -> str:
    return f"judge-me-review:{review_id}"


def _review_message_key(review_id: str) -> str:
    return f"judge-me-review-message:{review_id}"


async def sync_judge_me_reviews(
    db: AsyncSession,
    *,
    channel: CustomerChannel,
    client: JudgeMeClient | None = None,
) -> dict:
    """同步 Judge.me 评价，只为中差评创建需要卖家介入的工作项。"""

    credentials = json.loads(
        decrypt_value(channel.credentials_ciphertext)
    )
    reviews = await (client or JudgeMeHTTPClient()).fetch_reviews(
        credentials=credentials
    )
    created = 0
    duplicates = 0
    work_items_created = 0

    for review in reviews:
        message_key = _review_message_key(review.review_id)
        existing_message = (
            await db.execute(
                select(CustomerMessage).where(
                    CustomerMessage.workspace_id == channel.workspace_id,
                    CustomerMessage.external_message_id == message_key,
                )
            )
        ).scalar_one_or_none()
        if existing_message is not None:
            duplicates += 1
            continue

        thread_key = _review_thread_key(review.review_id)
        thread = (
            await db.execute(
                select(CustomerThread).where(
                    CustomerThread.workspace_id == channel.workspace_id,
                    CustomerThread.channel_id == channel.id,
                    CustomerThread.external_thread_id == thread_key,
                )
            )
        ).scalar_one_or_none()
        language = detect_language(review.body)
        if thread is None:
            thread = CustomerThread(
                workspace_id=channel.workspace_id,
                channel_id=channel.id,
                external_thread_id=thread_key,
                thread_type="review",
                customer_ref=review.reviewer_name,
                customer_email_hash=(
                    _email_hash(review.reviewer_email)
                    if review.reviewer_email
                    else None
                ),
                customer_address_ciphertext=(
                    encrypt_value(review.reviewer_email)
                    if review.reviewer_email
                    else None
                ),
                related_product_id=review.product_external_id,
                subject=(
                    review.review_title
                    or review.product_title
                    or f"{review.rating} 星商品评价"
                )[:500],
                language=language,
                status="waiting_user" if review.rating <= 3 else "new",
                priority="high" if review.rating <= 2 else "normal",
            )
            db.add(thread)
            await db.flush()
        else:
            thread.unread_count += 1
            thread.subject = thread.subject or (
                review.review_title or review.product_title
            )
            thread.language = thread.language or language

        outbound_time = (
            review.updated_at
            or review.created_at
            or datetime.now(timezone.utc)
        )
        message = CustomerMessage(
            workspace_id=channel.workspace_id,
            thread_id=thread.id,
            external_message_id=message_key,
            direction="inbound",
            body_text=review.body,
            language=language,
            send_status="received",
        )
        db.add(message)
        created += 1
        thread.last_message_at = outbound_time

        # 好评不打断卖家。中差评只给出原文和明确下一步，不伪造 Agent 草稿。
        if review.rating <= 3:
            product_label = review.product_title or "商品"
            await create_work_item(
                db,
                workspace_id=channel.workspace_id,
                actor_user_id=channel.created_by_user_id,
                kind="review_reply",
                source="integration",
                title=f"{review.rating} 星评价需要回复：{product_label}"[:120],
                summary=(
                    review.body[:120]
                    or "买家留下中差评，Agent 需要先确认处理方式。"
                ),
                status="waiting_user",
                requires_action="input",
                current_step="等待你补充回复要求或提供售后处理方式",
                source_type="customer_thread",
                source_id=str(thread.id),
                result={
                    "review_id": review.review_id,
                    "rating": review.rating,
                    "product_external_id": review.product_external_id,
                    "product_title": review.product_title,
                },
            )
            work_items_created += 1

    channel.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "messages_scanned": len(reviews),
        "messages_created": created,
        "duplicates_skipped": duplicates,
        "work_items_created": work_items_created,
    }


def _review_id_from_thread(thread: CustomerThread) -> str:
    prefix = "judge-me-review:"
    raw = str(thread.external_thread_id or "")
    if not raw.startswith(prefix) or not raw[len(prefix):].isdigit():
        raise ValueError("评价线程缺少有效 Judge.me 编号")
    return raw[len(prefix):]


def _find_reply_text(payload: dict) -> str | None:
    """从公开 API 可能返回的字段中提取回复正文。"""

    candidates: list[Any] = [
        payload.get("reply"),
        payload.get("public_reply"),
        payload.get("reply_text"),
        payload.get("replies"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, dict):
            for key in ("content", "body", "text"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    for key in ("content", "body", "text"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
    return None


class JudgeMeReviewActionAdapter:
    """确认后公开发布评价回复，并明确区分回读核验与服务端已受理。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        user_id: UUID,
        client: JudgeMeClient | None = None,
    ):
        self.db = db
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.client = client or JudgeMeHTTPClient()

    async def _context(self, input_data: dict):
        try:
            channel_id = UUID(str(input_data["channel_id"]))
            thread_id = UUID(str(input_data["thread_id"]))
            draft_id = UUID(str(input_data["draft_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("评价回复参数不完整") from exc

        channel = await self.db.get(CustomerChannel, channel_id)
        thread = await self.db.get(CustomerThread, thread_id)
        draft = await self.db.get(ReplyDraft, draft_id)
        if (
            channel is None
            or channel.workspace_id != self.workspace_id
            or channel.provider != "judge_me"
            or channel.status != "active"
        ):
            raise ValueError("评价渠道不存在或已失效")
        if (
            thread is None
            or thread.workspace_id != self.workspace_id
            or thread.channel_id != channel.id
            or thread.thread_type != "review"
        ):
            raise ValueError("评价线程不存在或不属于当前工作区")
        if (
            draft is None
            or draft.workspace_id != self.workspace_id
            or draft.thread_id != thread.id
        ):
            raise ValueError("评价回复草稿不存在或与线程不匹配")

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
            raise ValueError("评价回复草稿已过期，请重新生成")
        if draft.status not in {"ready", "approved"}:
            raise ValueError("评价回复草稿当前不可发送")
        if not draft.body_text.strip():
            raise ValueError("评价回复正文不能为空")
        return channel, thread, draft

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "reviews.reply":
            raise ValueError("适配器不支持该动作")
        channel, thread, draft = await self._context(input_data)
        review_id = _review_id_from_thread(thread)
        if str(target_id) not in {review_id, str(thread.id)}:
            raise ValueError("动作目标评价与输入不一致")
        return {
            "channel_id": str(channel.id),
            "thread_id": str(thread.id),
            "draft_id": str(draft.id),
            "draft_version": draft.version,
            "review_id": review_id,
            "body_text": draft.body_text,
            "reviewer": thread.customer_ref,
            "product_external_id": thread.related_product_id,
            "send_reply_email": bool(
                input_data.get("send_reply_email", False)
            ),
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
            return ActionExecution(
                external_id=existing.external_message_id,
                output={
                    "idempotency_key": idempotency_key,
                    "thread_id": str(existing.thread_id),
                    "replayed": True,
                },
            )

        snapshot = await self.preflight(
            action_id=action_id,
            target_id=target_id,
            input_data=input_data,
        )
        channel, thread, draft = await self._context(input_data)
        credentials = json.loads(
            decrypt_value(channel.credentials_ciphertext)
        )
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
        # 先落发送中记录，进程中断后可以据此对账而不是盲目重发。
        await self.db.commit()

        try:
            receipt = await self.client.create_public_reply(
                credentials=credentials,
                review_id=str(snapshot["review_id"]),
                body_text=draft.body_text,
                send_reply_email=bool(snapshot["send_reply_email"]),
                idempotency_key=idempotency_key,
            )
            if not receipt.accepted:
                raise JudgeMeAPIError("Judge.me 未确认公开回复已受理")
        except Exception:
            outbound.send_status = "failed"
            await self.db.commit()
            raise

        outbound.external_message_id = receipt.external_id
        outbound.send_status = "sent"
        outbound.sent_at = datetime.now(timezone.utc)
        draft.status = "sent"
        thread.status = "resolved"
        thread.last_message_at = outbound.sent_at
        await self.db.commit()
        return ActionExecution(
            external_id=receipt.external_id,
            output={
                "idempotency_key": idempotency_key,
                "thread_id": str(thread.id),
                "channel_id": str(channel.id),
                "review_id": str(snapshot["review_id"]),
                "body_text": draft.body_text,
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
                details={"error": "回读找不到评价回复记录"},
            )
        local_matched = (
            message.send_status == "sent"
            and message.external_message_id == execution.external_id
        )
        if not local_matched:
            return ActionVerification(
                matched=False,
                details={
                    "idempotency_key": key,
                    "mismatches": ["send_status", "external_message_id"],
                },
            )

        thread = await self.db.get(CustomerThread, message.thread_id)
        channel = (
            await self.db.get(CustomerChannel, thread.channel_id)
            if thread is not None
            else None
        )
        if channel is None:
            return ActionVerification(
                matched=False,
                details={"error": "回读找不到评价渠道"},
            )
        review_id = str(output.get("review_id") or "")
        credentials = json.loads(
            decrypt_value(channel.credentials_ciphertext)
        )
        try:
            remote = await self.client.read_review(
                credentials=credentials,
                review_id=review_id,
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={
                    "idempotency_key": key,
                    "error": f"公开回复回读失败：{str(exc)[:160]}",
                },
            )

        remote_reply = _find_reply_text(remote)
        if remote_reply is None:
            return ActionVerification(
                matched=True,
                snapshot={
                    "message_id": str(message.id),
                    "external_message_id": message.external_message_id,
                    "send_status": message.send_status,
                    "review_id": review_id,
                },
                details={
                    "idempotency_key": key,
                    # Judge.me 当前公开文档未承诺评价详情返回回复正文。
                    "verification_level": "api_accepted",
                    "external_readback_supported": False,
                    "warning": "Judge.me 已受理回复，但公开 API 未返回可核验的回复正文。",
                },
            )

        matched = message.body_text.strip() == remote_reply
        return ActionVerification(
            matched=matched,
            snapshot={
                "message_id": str(message.id),
                "external_message_id": message.external_message_id,
                "send_status": message.send_status,
                "review_id": review_id,
                "remote_reply": remote_reply,
            },
            details={
                "idempotency_key": key,
                "verification_level": "external_readback",
                "external_readback_supported": True,
                "mismatches": [] if matched else ["reply_text"],
            },
        )
