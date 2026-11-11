"""Shopify 订单销量与已发布商品库存同步。"""

from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.core.config import settings
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User


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

    try:
        async with httpx.AsyncClient() as client:
            orders: list[dict] = []
            page_info = ""
            for _ in range(10):
                params = (
                    {
                        "limit": 250,
                        "page_info": page_info,
                        "fields": "id,created_at,line_items,financial_status,cancelled_at",
                    }
                    if page_info
                    else {
                        "status": "any",
                        "limit": 250,
                        "created_at_min": created_at_min,
                        "fields": "id,created_at,line_items,financial_status,cancelled_at",
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
        "unmatched_skus": unmatched[:100],
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
