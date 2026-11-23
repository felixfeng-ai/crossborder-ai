"""Shopify 库存与本地 SKU 的增量对账信号。"""

from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.agent_signal import IntegrationCursor
from app.models.product_variant import ProductVariant
from app.models.shopify_channel import ShopifyChannel
from app.services.agent_signals import (
    ingest_agent_signal,
    resolve_latest_signal_by_fingerprint,
    save_integration_cursor,
)
from app.services.shopify_order_signal_sync import (
    ShopifyAuthorizationError,
    ShopifyRateLimitError,
)
from app.services.integration_events import (
    claim_integration_lease,
    release_integration_lease,
)


LOW_STOCK_THRESHOLD = 5


def _domain(channel: ShopifyChannel) -> str:
    domain = (channel.shop_domain or "").strip()
    if domain:
        return domain
    name = (channel.shop_name or "").replace(".myshopify.com", "").strip()
    return f"{name}.myshopify.com"


def _fingerprint(channel_id, sku: str, kind: str) -> str:
    return f"shopify-inventory:{channel_id}:{sku}:{kind}"


async def sync_shopify_inventory_signals(
    db: AsyncSession,
    *,
    workspace_id,
    channel: ShopifyChannel,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """读取 Shopify SKU 库存，只生成信号，不自动覆盖本地库存。"""

    if channel.workspace_id not in (None, workspace_id):
        raise ValueError("Shopify 渠道不属于当前工作区")
    cursor = (
        await db.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace_id,
                IntegrationCursor.channel_id == str(channel.id),
                IntegrationCursor.resource_type == "shopify_inventory",
            )
        )
    ).scalar_one_or_none()
    params = {
        "limit": 250,
        "fields": "id,title,updated_at,variants",
    }
    if cursor is not None:
        params["updated_at_min"] = cursor.cursor_value
    url = (
        f"https://{_domain(channel)}"
        f"/admin/api/{settings.SHOPIFY_API_VERSION}/products.json"
    )
    headers = {
        "X-Shopify-Access-Token": decrypt_value(channel.access_token),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(transport=transport, timeout=20) as client:
        response = await client.get(url, headers=headers, params=params)
    if response.status_code == 429:
        raise ShopifyRateLimitError(
            "Shopify 库存同步限流，稍后从游标继续"
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
            summary="请重新连接店铺后继续同步库存。",
            payload={"channel_id": str(channel.id)},
            fingerprint=f"shopify-channel:{channel.id}:authorization",
            channel_type="shopify",
            channel_id=str(channel.id),
        )
        raise ShopifyAuthorizationError("Shopify 店铺授权已失效")
    if response.status_code != 200:
        raise RuntimeError(f"读取 Shopify 库存失败：{response.text[:200]}")

    variants = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.user_id == channel.user_id,
            )
        )
    ).scalars().all()
    variant_by_sku = {variant.sku: variant for variant in variants}
    created = 0
    updated = 0
    resolved = 0
    latest_updated_at = cursor.cursor_value if cursor else None
    for product in response.json().get("products") or []:
        updated_at = product.get("updated_at")
        if updated_at and (
            latest_updated_at is None or str(updated_at) > latest_updated_at
        ):
            latest_updated_at = str(updated_at)
        for remote_variant in product.get("variants") or []:
            sku = str(remote_variant.get("sku") or "").strip()
            local = variant_by_sku.get(sku)
            if local is None:
                continue
            try:
                remote_stock = max(
                    0,
                    int(remote_variant.get("inventory_quantity") or 0),
                )
            except (TypeError, ValueError):
                continue
            fingerprints = {
                "out_of_stock": _fingerprint(
                    channel.id,
                    sku,
                    "out-of-stock",
                ),
                "low": _fingerprint(channel.id, sku, "low"),
                "conflict": _fingerprint(channel.id, sku, "conflict"),
            }
            if remote_stock <= 0:
                target = "out_of_stock"
                signal_type = "inventory_out_of_stock"
                severity = "urgent"
                title = f"SKU {sku} 已在 Shopify 缺货"
                summary = "建议补货或暂停该 SKU 的销售和投放。"
            elif local.stock_quantity != remote_stock:
                target = "conflict"
                signal_type = "inventory_conflict"
                severity = "attention"
                title = f"SKU {sku} 库存与平台不一致"
                summary = (
                    f"本地库存 {local.stock_quantity}，"
                    f"Shopify 库存 {remote_stock}，请确认是否回写。"
                )
            elif remote_stock <= LOW_STOCK_THRESHOLD:
                target = "low"
                signal_type = "inventory_low"
                severity = "attention"
                title = f"SKU {sku} 即将售罄"
                summary = f"Shopify 库存仅剩 {remote_stock} 件。"
            else:
                target = None
                signal_type = None
                severity = None
                title = None
                summary = None

            for kind, fingerprint in fingerprints.items():
                if kind == target:
                    continue
                resolved_signal = await resolve_latest_signal_by_fingerprint(
                    db,
                    workspace_id=workspace_id,
                    fingerprint=fingerprint,
                    summary="库存状态已恢复或已由其他信号覆盖。",
                )
                if (
                    resolved_signal is not None
                    and resolved_signal.status == "resolved"
                ):
                    resolved += 1
            if target is not None:
                result = await ingest_agent_signal(
                    db,
                    workspace_id=workspace_id,
                    actor_user_id=channel.user_id,
                    source_type="inventory",
                    source_id=sku,
                    signal_type=signal_type,
                    severity=severity,
                    title=title,
                    summary=summary,
                    payload={
                        "sku": sku,
                        "local_stock": local.stock_quantity,
                        "remote_stock": remote_stock,
                        "threshold": LOW_STOCK_THRESHOLD,
                    },
                    fingerprint=fingerprints[target],
                    channel_type="shopify",
                    channel_id=str(channel.id),
                )
                if result.created:
                    created += 1
                else:
                    updated += 1

    if latest_updated_at:
        await save_integration_cursor(
            db,
            workspace_id=workspace_id,
            channel_id=str(channel.id),
            resource_type="shopify_inventory",
            cursor_value=latest_updated_at,
            overlap_seconds=600,
        )
    return {
        "products_scanned": len(response.json().get("products") or []),
        "signals_created": created,
        "signals_updated": updated,
        "signals_resolved": resolved,
        "cursor_value": latest_updated_at,
    }


async def sync_all_shopify_inventory_signals(db: AsyncSession) -> dict:
    """同步已绑定工作区的渠道，单店失败隔离。"""

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
        "signals_created": 0,
        "signals_resolved": 0,
    }
    for channel in channels:
        owner = f"inventory-sync:{uuid4().hex}"
        lease = await claim_integration_lease(
            db,
            workspace_id=channel.workspace_id,
            channel_id=str(channel.id),
            resource_type="shopify_inventory",
            owner_token=owner,
        )
        await db.commit()
        if lease is None:
            summary["channels_skipped"] += 1
            continue
        try:
            result = await sync_shopify_inventory_signals(
                db,
                workspace_id=channel.workspace_id,
                channel=channel,
            )
            await db.commit()
            summary["channels_succeeded"] += 1
            summary["signals_created"] += result["signals_created"]
            summary["signals_resolved"] += result["signals_resolved"]
        except Exception:
            await db.rollback()
            summary["channels_failed"] += 1
        finally:
            await release_integration_lease(
                db,
                workspace_id=channel.workspace_id,
                channel_id=str(channel.id),
                resource_type="shopify_inventory",
                owner_token=owner,
            )
            await db.commit()
    return summary
