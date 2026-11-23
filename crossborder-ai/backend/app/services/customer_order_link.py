"""客户会话与 Shopify 订单事实的保守关联。"""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.action_run import ActionRun
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.customer_channel import CustomerOrderLink, CustomerThread
from app.models.customer_channel import ReplyDraft
from app.models.shopify_channel import ShopifyChannel


@dataclass(frozen=True)
class ShopifyOrderFact:
    """允许进入客服上下文的订单事实，不包含客户隐私字段。"""

    shopify_channel_id: str
    external_order_id: str
    order_name: str | None
    financial_status: str | None
    fulfillment_status: str | None
    order_created_at: datetime | None
    tracking_company: str | None
    tracking_number: str | None
    tracking_url: str | None
    snapshot: dict


@dataclass(frozen=True)
class OrderResolution:
    status: str
    candidate_count: int
    candidates: tuple[dict, ...] = ()


class ShopifyOrderClient(Protocol):
    async def find_orders(
        self,
        *,
        shopify_channel: ShopifyChannel,
        customer_email: str,
    ) -> list[ShopifyOrderFact]: ...


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class ShopifyOrderFactsClient:
    """通过 Shopify Admin REST 读取指定客户的订单与物流事实。"""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.transport = transport

    @staticmethod
    def _domain(channel: ShopifyChannel) -> str:
        domain = str(channel.shop_domain or "").strip()
        if domain:
            return domain
        name = str(channel.shop_name or "").replace(
            ".myshopify.com",
            "",
        ).strip()
        return f"{name}.myshopify.com"

    def _url(self, channel: ShopifyChannel, path: str) -> str:
        return (
            f"https://{self._domain(channel)}"
            f"/admin/api/{settings.SHOPIFY_API_VERSION}{path}"
        )

    @staticmethod
    def _headers(channel: ShopifyChannel) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": decrypt_value(channel.access_token),
            "Accept": "application/json",
        }

    async def _request(
        self,
        channel: ShopifyChannel,
        path: str,
        *,
        params: dict | None = None,
    ) -> dict:
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=20,
        ) as client:
            response = await client.get(
                self._url(channel, path),
                headers=self._headers(channel),
                params=params,
            )
        if response.status_code == 429:
            raise RuntimeError("Shopify 订单查询限流")
        if response.status_code in {401, 403}:
            raise RuntimeError("Shopify 店铺授权已失效")
        if response.status_code >= 400:
            raise RuntimeError(
                f"Shopify 订单查询失败：{response.text[:200]}"
            )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def find_orders(
        self,
        *,
        shopify_channel: ShopifyChannel,
        customer_email: str,
    ) -> list[ShopifyOrderFact]:
        email = customer_email.strip().lower()
        payload = await self._request(
            shopify_channel,
            "/orders.json",
            params={
                "email": email,
                "status": "any",
                "limit": 5,
                "fields": (
                    "id,name,email,financial_status,"
                    "fulfillment_status,created_at,updated_at"
                ),
            },
        )
        orders = payload.get("orders") or []
        facts: list[ShopifyOrderFact] = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            remote_email = str(order.get("email") or "").strip().lower()
            if remote_email and remote_email != email:
                continue
            order_id = str(order.get("id") or "").strip()
            if not order_id:
                continue
            fulfillments_payload = await self._request(
                shopify_channel,
                f"/orders/{order_id}/fulfillments.json",
            )
            fulfillments = fulfillments_payload.get("fulfillments") or []
            tracking = next(
                (
                    item
                    for item in fulfillments
                    if isinstance(item, dict)
                    and (
                        item.get("tracking_number")
                        or item.get("tracking_numbers")
                    )
                ),
                {},
            )
            tracking_numbers = tracking.get("tracking_numbers") or []
            tracking_number = str(
                tracking.get("tracking_number")
                or (tracking_numbers[0] if tracking_numbers else "")
                or ""
            ).strip()
            snapshot = {
                "id": order_id,
                "name": order.get("name"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "created_at": order.get("created_at"),
                "tracking_company": tracking.get("tracking_company"),
                "tracking_number": tracking_number or None,
                "tracking_url": tracking.get("tracking_url"),
            }
            facts.append(
                ShopifyOrderFact(
                    shopify_channel_id=str(shopify_channel.id),
                    external_order_id=order_id,
                    order_name=(
                        str(order.get("name") or "").strip() or None
                    ),
                    financial_status=(
                        str(order.get("financial_status") or "").strip()
                        or None
                    ),
                    fulfillment_status=(
                        str(order.get("fulfillment_status") or "").strip()
                        or None
                    ),
                    order_created_at=_parse_datetime(
                        order.get("created_at")
                    ),
                    tracking_company=(
                        str(tracking.get("tracking_company") or "").strip()
                        or None
                    ),
                    tracking_number=tracking_number or None,
                    tracking_url=(
                        str(tracking.get("tracking_url") or "").strip()
                        or None
                    ),
                    snapshot=snapshot,
                )
            )
        return facts


async def resolve_customer_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread: CustomerThread,
    client: ShopifyOrderClient | None = None,
) -> OrderResolution:
    """只有唯一定位一个订单时才建立关联，多订单明确返回歧义。"""

    if thread.workspace_id != workspace_id:
        raise ValueError("客户会话不属于当前工作区")
    if not thread.customer_address_ciphertext:
        return OrderResolution(status="no_customer_email", candidate_count=0)
    customer_email = decrypt_value(
        thread.customer_address_ciphertext
    ).strip().lower()
    channels = (
        await db.execute(
            select(ShopifyChannel).where(
                ShopifyChannel.workspace_id == workspace_id,
                ShopifyChannel.is_active.is_(True),
            )
        )
    ).scalars().all()
    if not channels:
        return OrderResolution(status="no_channel", candidate_count=0)
    lookup = client or ShopifyOrderFactsClient()
    candidates: list[ShopifyOrderFact] = []
    for channel in channels:
        orders = await lookup.find_orders(
            shopify_channel=channel,
            customer_email=customer_email,
        )
        for order in orders:
            candidates.append(
                replace(
                    order,
                    shopify_channel_id=str(channel.id),
                )
            )
    if not candidates:
        return OrderResolution(status="not_found", candidate_count=0)
    if len(candidates) != 1:
        return OrderResolution(
            status="ambiguous",
            candidate_count=len(candidates),
            candidates=tuple(
                _safe_candidate(fact) for fact in candidates[:10]
            ),
        )

    fact = candidates[0]
    await _upsert_order_link(
        db,
        workspace_id=workspace_id,
        thread=thread,
        fact=fact,
    )
    return OrderResolution(
        status="linked",
        candidate_count=1,
        candidates=(_safe_candidate(fact),),
    )


def _safe_candidate(fact: ShopifyOrderFact) -> dict:
    return {
        "shopify_channel_id": fact.shopify_channel_id,
        "external_order_id": fact.external_order_id,
        "order_name": fact.order_name,
        "financial_status": fact.financial_status,
        "fulfillment_status": fact.fulfillment_status,
        "order_created_at": (
            fact.order_created_at.isoformat()
            if fact.order_created_at is not None
            else None
        ),
        "tracking_company": fact.tracking_company,
        "tracking_number": fact.tracking_number,
        "tracking_url": fact.tracking_url,
    }


async def _upsert_order_link(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread: CustomerThread,
    fact: ShopifyOrderFact,
) -> CustomerOrderLink:
    link = (
        await db.execute(
            select(CustomerOrderLink).where(
                CustomerOrderLink.workspace_id == workspace_id,
                CustomerOrderLink.thread_id == thread.id,
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    values = {
        "shopify_channel_id": UUID(fact.shopify_channel_id),
        "external_order_id": fact.external_order_id,
        "order_name": fact.order_name,
        "financial_status": fact.financial_status,
        "fulfillment_status": fact.fulfillment_status,
        "tracking_company": fact.tracking_company,
        "tracking_number": fact.tracking_number,
        "tracking_url": fact.tracking_url,
        "order_created_at": fact.order_created_at,
        "snapshot_json": json.dumps(
            fact.snapshot,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "fetched_at": now,
        "updated_at": now,
    }
    if link is None:
        link = CustomerOrderLink(
            workspace_id=workspace_id,
            thread_id=thread.id,
            **values,
        )
        db.add(link)
    else:
        for key, value in values.items():
            setattr(link, key, value)
    thread.related_order_id = fact.external_order_id
    await db.flush()
    return link


async def link_customer_order(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread: CustomerThread,
    shopify_channel_id: UUID,
    external_order_id: str,
    client: ShopifyOrderClient | None = None,
) -> OrderResolution:
    """卖家选择候选后重新向 Shopify 校验，再建立或切换订单关联。"""

    if thread.workspace_id != workspace_id:
        raise ValueError("客户会话不属于当前工作区")
    if not thread.customer_address_ciphertext:
        return OrderResolution(status="no_customer_email", candidate_count=0)
    channel = (
        await db.execute(
            select(ShopifyChannel).where(
                ShopifyChannel.id == shopify_channel_id,
                ShopifyChannel.workspace_id == workspace_id,
                ShopifyChannel.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if channel is None:
        raise ValueError("Shopify 店铺不存在或不属于当前工作区")
    customer_email = decrypt_value(
        thread.customer_address_ciphertext
    ).strip().lower()
    orders = await (client or ShopifyOrderFactsClient()).find_orders(
        shopify_channel=channel,
        customer_email=customer_email,
    )
    matched = next(
        (
            order
            for order in orders
            if order.external_order_id == str(external_order_id)
        ),
        None,
    )
    if matched is None:
        return OrderResolution(status="not_found", candidate_count=0)
    matched = replace(
        matched,
        shopify_channel_id=str(channel.id),
    )
    await _upsert_order_link(
        db,
        workspace_id=workspace_id,
        thread=thread,
        fact=matched,
    )
    return OrderResolution(
        status="linked",
        candidate_count=1,
        candidates=(_safe_candidate(matched),),
    )


async def apply_customer_order_selection(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread: CustomerThread,
    work_item: WorkItem,
    shopify_channel_id: UUID,
    external_order_id: str,
    client: ShopifyOrderClient | None = None,
) -> OrderResolution:
    """卖家选中候选订单后，失效旧产物并重新入队值班任务。"""

    old_order_id = thread.related_order_id
    resolution = await link_customer_order(
        db,
        workspace_id=workspace_id,
        thread=thread,
        shopify_channel_id=shopify_channel_id,
        external_order_id=external_order_id,
        client=client,
    )
    if resolution.status != "linked":
        return resolution

    if old_order_id and old_order_id != str(external_order_id):
        drafts = (
            await db.execute(
                select(ReplyDraft).where(
                    ReplyDraft.workspace_id == workspace_id,
                    ReplyDraft.thread_id == thread.id,
                    ReplyDraft.status.in_(
                        ["generating", "ready", "approved"]
                    ),
                )
            )
        ).scalars().all()
        for draft in drafts:
            draft.status = "stale"
        runs = (
            await db.execute(
                select(ActionRun).where(
                    ActionRun.workspace_id == workspace_id,
                    ActionRun.work_item_id == work_item.id,
                    ActionRun.action_id == "messages.reply",
                    ActionRun.status.in_(
                        ["planned", "awaiting_confirmation", "queued"]
                    ),
                )
            )
        ).scalars().all()
        for run in runs:
            run.status = "cancelled"
            run.error_code = "order_changed"
            run.version += 1

    try:
        result = json.loads(work_item.result_json or "{}")
    except json.JSONDecodeError:
        result = {}
    result.update(
        {
            "order_lookup_status": "linked",
            "order_candidate_count": 1,
            "order_candidates": [],
            "selected_order_id": str(external_order_id),
            "selection_source": "seller",
        }
    )
    work_item.result_json = json.dumps(result, ensure_ascii=False)
    work_item.status = "running"
    work_item.requires_action = "none"
    work_item.priority = "normal"
    work_item.current_step = "订单已选择，Agent 正在重新生成回复"
    work_item.version += 1
    db.add(
        WorkItemEvent(
            workspace_id=workspace_id,
            work_item_id=work_item.id,
            event_type="customer_order.selected",
            actor_user_id=None,
            payload_json=json.dumps(
                {
                    "thread_id": str(thread.id),
                    "previous_order_id": old_order_id,
                    "selected_order_id": str(external_order_id),
                },
                ensure_ascii=False,
            ),
        )
    )
    await db.flush()
    # 延迟导入避免订单服务与 Worker 模块在加载时循环依赖。
    from app.services.customer_reply_worker import (
        enqueue_customer_reply_tasks,
    )

    await enqueue_customer_reply_tasks(db, limit=50)
    return resolution
