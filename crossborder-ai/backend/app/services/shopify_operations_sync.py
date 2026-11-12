"""Shopify 订单销量与已发布商品库存同步。"""

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.core.config import settings
from app.models.product_variant import ProductVariant
from app.models.marketing_distribution import (
    MarketingCampaignPublication,
    MarketingPerformanceSnapshot,
)
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.automation_settings import (
    automation_enabled_for_user,
    record_task_state,
)


class ShopifyOperationsSyncError(Exception):
    """Shopify 运营同步失败。"""


def _channel_domain(channel: ShopifyChannel) -> str:
    domain = (getattr(channel, "shop_domain", "") or "").strip()
    if domain:
        return domain
    shop_name = (channel.shop_name or "").replace(".myshopify.com", "").strip()
    return f"{shop_name}.myshopify.com"


def aggregate_order_sales(orders: Iterable[dict], *, days: int) -> dict[str, float]:
    """按 SKU 汇总订单件数并转换为日均销量。"""
    safe_days = max(1, int(days))
    quantities: dict[str, int] = {}
    for order in orders:
        if order.get("cancelled_at"):
            continue
        if order.get("financial_status") in {"refunded", "voided"}:
            continue
        for item in order.get("line_items") or []:
            sku = str(item.get("sku") or "").strip()
            try:
                quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0
            if not sku or quantity <= 0:
                continue
            quantities[sku] = quantities.get(sku, 0) + quantity
    return {
        sku: round(quantity / safe_days, 4)
        for sku, quantity in quantities.items()
    }


def aggregate_campaign_order_metrics(
    orders: Iterable[dict],
    campaign_by_external_product: dict[str, list],
) -> dict:
    """按 Shopify 商品 ID 汇总活动订单数和销售额。"""
    metrics: dict = {}
    for order in orders:
        if order.get("cancelled_at"):
            continue
        if order.get("financial_status") in {"refunded", "voided"}:
            continue
        matched_campaigns: set = set()
        for item in order.get("line_items") or []:
            external_product_id = str(item.get("product_id") or "").strip()
            campaign_ids = campaign_by_external_product.get(external_product_id) or []
            if not campaign_ids:
                continue
            try:
                quantity = max(0, int(item.get("quantity") or 0))
                price = max(0.0, float(item.get("price") or 0))
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue
            for campaign_id in campaign_ids:
                bucket = metrics.setdefault(
                    campaign_id,
                    {
                        "orders": 0,
                        "revenue": 0.0,
                        "currency": str(order.get("currency") or "USD"),
                        "line_units": 0,
                    },
                )
                bucket["revenue"] = round(
                    float(bucket["revenue"]) + price * quantity,
                    2,
                )
                bucket["line_units"] += quantity
                matched_campaigns.add(campaign_id)
        for campaign_id in matched_campaigns:
            metrics[campaign_id]["orders"] += 1
    return metrics


def _next_page_info(link_header: str | None) -> str:
    """从 Shopify Link 响应头提取下一页 page_info。"""
    for part in (link_header or "").split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start < 0 or end <= start:
            continue
        query = parse_qs(urlparse(part[start + 1:end]).query)
        return (query.get("page_info") or [""])[0]
    return ""


def extract_stock_by_sku(products: Iterable[dict]) -> dict[str, int]:
    """从 Shopify Product Variants 提取 SKU 库存。"""
    stock_by_sku: dict[str, int] = {}
    for product in products:
        for variant in product.get("variants") or []:
            sku = str(variant.get("sku") or "").strip()
            quantity = variant.get("inventory_quantity")
            if not sku or quantity is None:
                continue
            try:
                stock_by_sku[sku] = max(0, int(quantity))
            except (TypeError, ValueError):
                continue
    return stock_by_sku


async def sync_shopify_operations(
    db: AsyncSession,
    *,
    user: User,
    channel: ShopifyChannel,
    days: int = 30,
) -> dict:
    """同步最近订单销量与本平台已发布商品库存。"""
    safe_days = max(1, min(int(days), 365))
    shop_url = (
        f"https://{_channel_domain(channel)}"
        f"/admin/api/{settings.SHOPIFY_API_VERSION}"
    )
    headers = {
        "X-Shopify-Access-Token": decrypt_value(channel.access_token),
        "Content-Type": "application/json",
    }
    created_at_min = (
        datetime.now(timezone.utc) - timedelta(days=safe_days)
    ).isoformat()

    publications = (
        await db.execute(
            select(Publication).where(
                Publication.user_id == user.id,
                Publication.platform == "shopify",
                Publication.channel_id == str(channel.id),
                Publication.status == "completed",
            )
        )
    ).scalars().all()
    external_product_ids = [
        item.external_product_id
        for item in publications
        if item.external_product_id
    ]
    campaign_publications = (
        await db.execute(
            select(MarketingCampaignPublication).where(
                MarketingCampaignPublication.user_id == user.id,
                MarketingCampaignPublication.platform == "shopify",
                MarketingCampaignPublication.channel_id == str(channel.id),
                MarketingCampaignPublication.status == "completed",
                MarketingCampaignPublication.external_product_id.is_not(None),
            )
        )
    ).scalars().all()
    campaign_by_external_product: dict[str, list] = {}
    for item in campaign_publications:
        key = str(item.external_product_id or "").strip()
        if not key:
            continue
        campaign_by_external_product.setdefault(key, []).append(item.campaign_id)

    try:
        async with httpx.AsyncClient() as client:
            orders: list[dict] = []
            page_info = ""
            for _ in range(10):
                params = (
                    {
                        "limit": 250,
                        "page_info": page_info,
                        "fields": "id,created_at,line_items,financial_status,cancelled_at,currency",
                    }
                    if page_info
                    else {
                        "status": "any",
                        "limit": 250,
                        "created_at_min": created_at_min,
                        "fields": "id,created_at,line_items,financial_status,cancelled_at,currency",
                    }
                )
                orders_response = await client.get(
                    f"{shop_url}/orders.json",
                    headers=headers,
                    params=params,
                )
                if orders_response.status_code != 200:
                    raise ShopifyOperationsSyncError(
                        f"读取 Shopify 订单失败：{orders_response.text[:160]}"
                    )
                orders.extend(orders_response.json().get("orders") or [])
                page_info = _next_page_info(
                    orders_response.headers.get("Link")
                    or orders_response.headers.get("link")
                )
                if not page_info:
                    break

            products: list[dict] = []
            if external_product_ids:
                products_response = await client.get(
                    f"{shop_url}/products.json",
                    headers=headers,
                    params={
                        "ids": ",".join(external_product_ids),
                        "fields": "id,variants",
                        "limit": 250,
                    },
                )
                if products_response.status_code != 200:
                    raise ShopifyOperationsSyncError(
                        f"读取 Shopify 商品库存失败：{products_response.text[:160]}"
                    )
                products = products_response.json().get("products") or []
    except ShopifyOperationsSyncError:
        raise
    except Exception as exc:
        raise ShopifyOperationsSyncError("Shopify 运营数据同步请求失败") from exc

    sales_by_sku = aggregate_order_sales(orders, days=safe_days)
    stock_by_sku = extract_stock_by_sku(products)
    sync_skus = set(sales_by_sku) | set(stock_by_sku)
    variants = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.user_id == user.id,
                ProductVariant.sku.in_(sync_skus),
            )
        )
    ).scalars().all() if sync_skus else []
    variant_by_sku = {item.sku: item for item in variants}

    sales_rate_updates = 0
    stock_updates = 0
    for sku, rate in sales_by_sku.items():
        variant = variant_by_sku.get(sku)
        if variant is not None:
            variant.daily_sales_rate = rate
            sales_rate_updates += 1
    for sku, stock in stock_by_sku.items():
        variant = variant_by_sku.get(sku)
        if variant is not None:
            variant.stock_quantity = stock
            stock_updates += 1

    campaign_metrics = aggregate_campaign_order_metrics(
        orders,
        campaign_by_external_product,
    )
    now = datetime.now(timezone.utc)
    period_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    period_start = (
        period_end.replace(hour=0, minute=0, second=0)
        - timedelta(days=safe_days - 1)
    )
    for campaign_id, values in campaign_metrics.items():
        snapshot = (
            await db.execute(
                select(MarketingPerformanceSnapshot).where(
                    MarketingPerformanceSnapshot.user_id == user.id,
                    MarketingPerformanceSnapshot.campaign_id == campaign_id,
                    MarketingPerformanceSnapshot.platform == "shopify",
                    MarketingPerformanceSnapshot.source == "shopify_orders",
                    MarketingPerformanceSnapshot.scope_key == "",
                    MarketingPerformanceSnapshot.period_start == period_start,
                    MarketingPerformanceSnapshot.period_end == period_end,
                )
            )
        ).scalar_one_or_none()
        if snapshot is None:
            snapshot = MarketingPerformanceSnapshot(
                user_id=user.id,
                campaign_id=campaign_id,
                platform="shopify",
                source="shopify_orders",
                scope_key="",
                period_start=period_start,
                period_end=period_end,
            )
        snapshot.impressions = 0
        snapshot.copy_id = None
        snapshot.scope_key = ""
        snapshot.clicks = 0
        snapshot.orders = int(values["orders"])
        snapshot.conversions = int(values["orders"])
        snapshot.spend = 0
        snapshot.revenue = float(values["revenue"])
        snapshot.currency = str(values["currency"] or "USD")
        snapshot.metadata_json = json.dumps(
            {
                "shopify_orders_scanned": len(orders),
                "matched_line_units": values["line_units"],
            },
            ensure_ascii=False,
        )
        db.add(snapshot)

    await db.commit()
    unmatched = sorted(sync_skus - set(variant_by_sku))
    return {
        "channel_id": str(channel.id),
        "shop_domain": _channel_domain(channel),
        "days": safe_days,
        "orders_scanned": len(orders),
        "products_scanned": len(products),
        "sales_rate_updates": sales_rate_updates,
        "stock_updates": stock_updates,
        "campaign_performance_updates": len(campaign_metrics),
        "unmatched_skus": unmatched[:100],
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


async def sync_all_shopify_operations(
    db: AsyncSession,
    *,
    days: int = 30,
) -> dict:
    """同步所有启用店铺，并隔离单店失败。

    一个失效 Token 不能阻断其他用户。失败后回滚当前事务，确保下一条
    店铺从干净会话开始；成功记录由同步服务自行提交。
    """
    channel_refs = (
        await db.execute(
            select(
                ShopifyChannel.id,
                ShopifyChannel.user_id,
                ShopifyChannel.shop_name,
                ShopifyChannel.shop_domain,
            )
            .where(ShopifyChannel.is_active.is_(True))
            .order_by(ShopifyChannel.created_at, ShopifyChannel.id)
        )
    ).all()

    summary = {
        "channels_scanned": len(channel_refs),
        "channels_succeeded": 0,
        "channels_failed": 0,
        "channels_skipped": 0,
        "orders_scanned": 0,
        "campaign_performance_updates": 0,
        "failures": [],
    }
    for channel_id, user_id, shop_name, shop_domain in channel_refs:
        domain = (
            str(shop_domain or "").strip()
            or f"{str(shop_name or '').replace('.myshopify.com', '').strip()}.myshopify.com"
        )
        user = await db.get(User, user_id)
        channel = await db.get(ShopifyChannel, channel_id)
        if channel is None:
            summary["channels_failed"] += 1
            summary["failures"].append(
                {
                    "channel_id": str(channel_id),
                    "shop_domain": domain,
                    "error": "店铺不存在或已删除",
                }
            )
            continue
        if user is None:
            summary["channels_failed"] += 1
            summary["failures"].append(
                {
                    "channel_id": str(channel_id),
                    "shop_domain": domain,
                    "error": "店铺所属用户不存在",
                }
            )
            continue
        if not await automation_enabled_for_user(db, user, "shopify_sync"):
            summary["channels_skipped"] += 1
            continue
        try:
            result = await sync_shopify_operations(
                db,
                user=user,
                channel=channel,
                days=days,
            )
            await record_task_state(
                db,
                user_id=user_id,
                task="shopify_sync",
                status="success",
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            summary["channels_failed"] += 1
            summary["failures"].append(
                {
                    "channel_id": str(channel_id),
                    "shop_domain": domain,
                    "error": str(exc)[:300],
                }
            )
            await record_task_state(
                db,
                user_id=user_id,
                task="shopify_sync",
                status="failed",
                error=str(exc),
            )
            await db.commit()
            continue

        summary["channels_succeeded"] += 1
        summary["orders_scanned"] += int(result.get("orders_scanned") or 0)
        summary["campaign_performance_updates"] += int(
            result.get("campaign_performance_updates") or 0
        )
    return summary
