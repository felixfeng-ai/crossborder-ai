"""Shopify 订单增量轮询到 Agent 信号。"""

from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.agent_signal import IntegrationCursor
from app.models.shopify_channel import ShopifyChannel
from app.services.agent_signals import (
    ingest_agent_signal,
    resolve_latest_signal_by_fingerprint,
    save_integration_cursor,
)
from app.services.integration_events import (
    claim_integration_lease,
    release_integration_lease,
)


class ShopifyRateLimitError(RuntimeError):
    """平台限流，调用方应退避而不是打扰用户。"""


class ShopifyAuthorizationError(RuntimeError):
    """店铺授权失效，需要创建重新授权任务。"""


def _domain(channel: ShopifyChannel) -> str:
    domain = (channel.shop_domain or "").strip()
    if domain:
        return domain
    name = (channel.shop_name or "").replace(".myshopify.com", "").strip()
    return f"{name}.myshopify.com"


def _order_commerce(order: dict) -> dict | None:
    """把 Shopify 订单压成前端能直接渲染的交易事实。

    金额保持平台返回的字符串（转 float 会丢精度），币种必须同行，
    否则美元店铺会被渲染成「¥1284」。缩略图只取前三张，多了列表行会挤变形。
    """
    total = order.get("total_price")
    currency = order.get("currency")

    thumbnails: list[str] = []
    for item in order.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        image = item.get("image")
        src = image.get("src") if isinstance(image, dict) else None
        if isinstance(src, str) and src.startswith(("http://", "https://")):
            thumbnails.append(src)
        if len(thumbnails) >= 3:
            break

    if total is None and not thumbnails:
        return None

    return {
        "amount": str(total).strip() if total is not None else None,
        "currency": str(currency).strip().upper() if currency else None,
        # 一个工作项对应一笔订单；跨订单聚合属于另一套业务规则，不在这里假定。
        "order_count": 1,
        "thumbnails": thumbnails,
    }


async def sync_shopify_order_signals(
    db: AsyncSession,
    *,
    workspace_id,
    channel: ShopifyChannel,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """读取增量订单，未履约订单进入信号，已履约订单关闭旧信号。"""

    if channel.workspace_id not in (None, workspace_id):
        raise ValueError("Shopify 渠道不属于当前工作区")
    cursor = (
        await db.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace_id,
                IntegrationCursor.channel_id == str(channel.id),
                IntegrationCursor.resource_type == "shopify_orders",
            )
        )
    ).scalar_one_or_none()
    params = {
        "status": "any",
        "limit": 250,
        "fields": "id,name,created_at,updated_at,fulfillment_status,"
        "financial_status,cancelled_at,total_price,currency,line_items",
    }
    if cursor is not None:
        params["updated_at_min"] = cursor.cursor_value

    url = (
        f"https://{_domain(channel)}"
        f"/admin/api/{settings.SHOPIFY_API_VERSION}/orders.json"
    )
    headers = {
        "X-Shopify-Access-Token": decrypt_value(channel.access_token),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(transport=transport, timeout=20) as client:
        response = await client.get(url, headers=headers, params=params)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise ShopifyRateLimitError(
            f"Shopify 限流，建议 {retry_after or '60'} 秒后重试"
        )
    if response.status_code == 401:
        await ingest_agent_signal(
            db,
            workspace_id=workspace_id,
            actor_user_id=channel.user_id,
            source_type="platform_connection",
            source_id=str(channel.id),
            signal_type="authorization_expired",
            severity="urgent",
            title="Shopify 店铺授权已失效",
            summary="请重新连接店铺后继续同步订单。",
            payload={"channel_id": str(channel.id)},
            fingerprint=f"shopify-channel:{channel.id}:authorization",
            channel_type="shopify",
            channel_id=str(channel.id),
        )
        raise ShopifyAuthorizationError("Shopify 店铺授权已失效")
    if response.status_code != 200:
        raise RuntimeError(f"读取 Shopify 订单失败：{response.text[:200]}")

    orders = response.json().get("orders") or []
    created = 0
    updated = 0
    resolved = 0
    latest_updated_at = cursor.cursor_value if cursor else None
    for order in orders:
        if not isinstance(order, dict) or order.get("id") is None:
            continue
        order_id = str(order["id"])
        fingerprint = f"shopify-order:{channel.id}:{order_id}:unfulfilled"
        is_closed = (
            order.get("fulfilled_status") == "fulfilled"
            or order.get("fulfillment_status") == "fulfilled"
            or bool(order.get("cancelled_at"))
        )
        if is_closed:
            if await resolve_latest_signal_by_fingerprint(
                db,
                workspace_id=workspace_id,
                fingerprint=fingerprint,
                summary="订单已完成履约或已取消。",
            ) is not None:
                resolved += 1
            continue

        age_hours = 0
        try:
            created_at = datetime.fromisoformat(
                str(order.get("created_at") or "").replace("Z", "+00:00")
            )
            age_hours = max(
                0,
                int(
                    (
                        datetime.now(timezone.utc) - created_at
                    ).total_seconds()
                    // 3600
                ),
            )
        except (TypeError, ValueError):
            created_at = None
        severity = (
            "urgent"
            if age_hours >= 48
            else "attention"
            if age_hours >= 24
            else "normal"
        )
        payload = {
            "order_id": order_id,
            "order_name": order.get("name"),
            "age_hours": age_hours,
        }
        commerce = _order_commerce(order)
        if commerce is not None:
            payload["commerce"] = commerce
        result = await ingest_agent_signal(
            db,
            workspace_id=workspace_id,
            actor_user_id=channel.user_id,
            source_type="shopify_order",
            source_id=order_id,
            signal_type="order_awaiting_shipment",
            severity=severity,
            title="有一笔订单等待发货",
            summary=(
                "订单等待时间较长，建议今天完成履约。"
                if age_hours >= 24
                else "Agent 正在关注订单履约状态。"
            ),
            payload=payload,
            fingerprint=fingerprint,
            channel_type="shopify",
            channel_id=str(channel.id),
        )
        if result.created:
            created += 1
        else:
            updated += 1
        updated_at = order.get("updated_at")
        if updated_at and (
            latest_updated_at is None or str(updated_at) > latest_updated_at
        ):
            latest_updated_at = str(updated_at)

    if latest_updated_at:
        await save_integration_cursor(
            db,
            workspace_id=workspace_id,
            channel_id=str(channel.id),
            resource_type="shopify_orders",
            cursor_value=latest_updated_at,
            overlap_seconds=300,
        )
    return {
        "orders_scanned": len(orders),
        "signals_created": created,
        "signals_updated": updated,
        "signals_resolved": resolved,
        "cursor_value": latest_updated_at,
    }


async def sync_all_shopify_order_signals(db: AsyncSession) -> dict:
    """同步已绑定工作区的店铺，单店限流或授权失败不阻塞其他店铺。"""

    channels = (
        await db.execute(
            select(ShopifyChannel).where(
                ShopifyChannel.is_active.is_(True),
                ShopifyChannel.workspace_id.is_not(None),
            )
        )
    ).scalars().all()
    summary = {
        "channels_scanned": len(channels),
        "channels_succeeded": 0,
        "channels_failed": 0,
        "channels_skipped": 0,
        "channels_rate_limited": 0,
        "signals_created": 0,
        "signals_resolved": 0,
        "failures": [],
    }
    for channel in channels:
        owner = f"order-sync:{uuid4().hex}"
        lease = await claim_integration_lease(
            db,
            workspace_id=channel.workspace_id,
            channel_id=str(channel.id),
            resource_type="shopify_orders",
            owner_token=owner,
        )
        await db.commit()
        if lease is None:
            summary["channels_skipped"] += 1
            continue
        try:
            result = await sync_shopify_order_signals(
                db,
                workspace_id=channel.workspace_id,
                channel=channel,
            )
            await db.commit()
            summary["channels_succeeded"] += 1
            summary["signals_created"] += result["signals_created"]
            summary["signals_resolved"] += result["signals_resolved"]
        except ShopifyRateLimitError as exc:
            await db.rollback()
            summary["channels_rate_limited"] += 1
            summary["failures"].append(
                {"channel_id": str(channel.id), "error": str(exc)}
            )
        except Exception as exc:
            await db.rollback()
            summary["channels_failed"] += 1
            summary["failures"].append(
                {"channel_id": str(channel.id), "error": str(exc)[:200]}
            )
        finally:
            await release_integration_lease(
                db,
                workspace_id=channel.workspace_id,
                channel_id=str(channel.id),
                resource_type="shopify_orders",
                owner_token=owner,
            )
            await db.commit()
    return summary
