"""Shopify 完整草稿商品发布服务。

网页发布与 AI Agent 必须共用本服务。Product.price 只表示 1688 供货参考价，
真正可发布的售价必须来自启用的 ProductVariant。
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Iterable, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.publication_service import (
    create_publication,
    find_publication_by_idempotency,
    publication_response,
)


class ShopifyPublishError(Exception):
    """带业务状态码的 Shopify 发布错误。"""

    def __init__(self, message: str, *, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class ShopifyPublishValidationError(ShopifyPublishError):
    """发布前数据不完整，调用方应提示用户补齐。"""

    def __init__(self, message: str):
        super().__init__(message, status_code=409)


@dataclass
class PreparedShopifyProduct:
    """已校验并转换好的 Shopify Product Payload。"""

    product: dict
    variant_count: int
    image_count: int


@dataclass
class ShopifyPublishResult:
    """一次发布或幂等重放的结果。"""

    publication: Publication
    prepared: Optional[PreparedShopifyProduct]
    replayed: bool = False


def _parse_attributes(raw: str | None) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
        if not isinstance(parsed, dict):
            return {}
        return {
            str(key).strip(): str(value).strip()
            for key, value in parsed.items()
            if str(key).strip() and str(value).strip()
        }
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_bullets(raw: str | None) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
        return [str(item).strip() for item in parsed if str(item).strip()]
    except (json.JSONDecodeError, TypeError):
        return []


def _single_line_text(raw: str | None, max_length: int) -> str:
    """把 SEO 文本压成 Shopify 单行元字段，并限制平台推荐长度。"""

    normalized = re.sub(r"\s+", " ", (raw or "").strip())
    return normalized[:max_length]


def _absolute_media_url(url: str | None, app_url: str) -> str:
    """把本地素材 URL 转成 Shopify 可抓取的绝对地址。"""
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith(("https://", "http://")):
        return value
    base = (app_url or settings.APP_URL).rstrip("/")
    if "localhost" in base or "127.0.0.1" in base:
        raise ShopifyPublishValidationError(
            "本地素材发布前必须配置公网 APP_URL，Shopify 无法访问 localhost"
        )
    if value.startswith("/"):
        return f"{base}{value}"
    return f"{base}/{value}"


def _build_media_images(
    product: Product,
    variants: Iterable[ProductVariant],
    *,
    app_url: str,
    listing_title: str,
) -> list[dict]:
    """合并主图和变体图，去重后作为商品媒体库发布。"""
    images: list[dict] = []
    seen: set[str] = set()

    def add(url: str | None, alt: str) -> None:
        src = _absolute_media_url(url, app_url)
        if not src or src in seen:
            return
        seen.add(src)
        images.append({"src": src, "alt": alt[:255]})

    add(product.main_image_url, listing_title or product.title or "Product")
    for variant in variants:
        add(variant.image_url, variant.sku)
    return images


def _build_body_html(description: str, bullets: list[str]) -> str:
    """保留描述富文本，并把五点卖点转成商品详情列表。"""
    parts: list[str] = []
    if description.strip():
        parts.append(description.strip())
    if bullets:
        items = "".join(f"<li>{escape(item)}</li>" for item in bullets)
        parts.append(f"<ul>{items}</ul>")
    return "\n".join(parts)


def build_shopify_product_payload(
    product: Product,
    listing: Optional[ListingDraft],
    variants: Iterable[ProductVariant],
    *,
    app_url: str | None = None,
) -> PreparedShopifyProduct:
    """构建并校验完整 Shopify 草稿商品 Payload。

    售价只读取启用 SKU 的 price。Product.price 是供货参考价，绝不进入
    Shopify variants；缺少售价时直接阻断，避免把采购价当零售价发布。
    """
    effective_app_url = app_url or settings.APP_URL
    active_variants = [item for item in variants if item.is_active]
    if not active_variants:
        raise ShopifyPublishValidationError(
            "发布前至少需要一个启用 SKU，请先在 SKU 中心创建并填写售价"
        )

    option_keys: list[str] = []
    attributes_by_variant: list[dict[str, str]] = []
    for variant in active_variants:
        attributes = _parse_attributes(variant.attributes_json)
        attributes_by_variant.append(attributes)
        for key in attributes:
            if key not in option_keys:
                option_keys.append(key)
    if len(option_keys) > 3:
        raise ShopifyPublishValidationError(
            "Shopify 单个商品最多支持三个变体属性，请精简 SKU 属性后重试"
        )

    option_values: dict[str, list[str]] = {key: [] for key in option_keys}
    for attributes in attributes_by_variant:
        for key in option_keys:
            value = attributes.get(key) or "Default"
            if value not in option_values[key]:
                option_values[key].append(value)

    variant_payloads: list[dict] = []
    for variant, attributes in zip(active_variants, attributes_by_variant):
        if variant.price is None or float(variant.price) <= 0:
            raise ShopifyPublishValidationError(
                f"SKU {variant.sku} 缺少大于 0 的销售价，请补齐后再发布"
            )
        payload = {
            "sku": variant.sku,
            "price": f"{float(variant.price):.2f}",
            "barcode": variant.barcode or "",
            "inventory_management": "shopify",
            "inventory_policy": "deny",
            "inventory_quantity": max(0, int(variant.stock_quantity or 0)),
        }
        if option_keys:
            for index, key in enumerate(option_keys, start=1):
                payload[f"option{index}"] = attributes.get(key) or "Default"
        else:
            payload["option1"] = "Default Title"
        variant_payloads.append(payload)

    title = (listing.title if listing else product.title) or "Untitled"
    description = (
        (listing.description if listing else product.description) or ""
    )
    bullets = _parse_bullets(listing.bullet_points if listing else None)
    images = _build_media_images(
        product,
        active_variants,
        app_url=effective_app_url,
        listing_title=title,
    )

    product_payload: dict = {
        "title": title,
        "body_html": _build_body_html(description, bullets),
        "status": "draft",
        "variants": variant_payloads,
    }
    if option_keys:
        product_payload["options"] = [
            {"name": key, "values": option_values[key]}
            for key in option_keys
        ]
    else:
        product_payload["options"] = [
            {"name": "Title", "values": ["Default Title"]}
        ]
    if images:
        product_payload["images"] = images
    if product.shop_name:
        product_payload["vendor"] = product.shop_name

    metafields: list[dict] = []
    if listing and listing.seo_title:
        metafields.append(
            {
                "namespace": "global",
                "key": "title_tag",
                "value": _single_line_text(listing.seo_title, 255),
                "type": "single_line_text_field",
            }
        )
    if listing and listing.seo_description:
        metafields.append(
            {
                "namespace": "global",
                "key": "description_tag",
                "value": _single_line_text(listing.seo_description, 320),
                "type": "single_line_text_field",
            }
        )
    if metafields:
        product_payload["metafields"] = metafields

    return PreparedShopifyProduct(
        product=product_payload,
        variant_count=len(variant_payloads),
        image_count=len(images),
    )


def _channel_domain(channel: ShopifyChannel) -> str:
    """优先使用规范化后的完整域名，兼容历史渠道数据。"""
    domain = (getattr(channel, "shop_domain", "") or "").strip()
    if domain:
        return domain
    shop_name = (channel.shop_name or "").replace(".myshopify.com", "").strip()
    return f"{shop_name}.myshopify.com"


async def _load_active_variants(
    db: AsyncSession,
    product: Product,
    user_id: UUID,
) -> list[ProductVariant]:
    return (
        await db.execute(
            select(ProductVariant)
            .where(
                ProductVariant.product_id == product.id,
                ProductVariant.user_id == user_id,
                ProductVariant.is_active.is_(True),
            )
            .order_by(ProductVariant.created_at, ProductVariant.sku)
        )
    ).scalars().all()


async def publish_shopify_product(
    db: AsyncSession,
    *,
    user: User,
    product: Product,
    listing: Optional[ListingDraft],
    channel: ShopifyChannel,
    idempotency_key: str = "",
    app_url: str | None = None,
) -> ShopifyPublishResult:
    """构建完整 Payload、调用 Shopify 并写入统一发布记录。"""
    existing = await find_publication_by_idempotency(
        db,
        user.id,
        "shopify",
        idempotency_key,
    )
    if existing is not None:
        if existing.status == "completed":
            return ShopifyPublishResult(
                publication=existing,
                prepared=None,
                replayed=True,
            )
        raise ShopifyPublishError(
            "相同发布请求正在处理或上次已失败，请使用新的幂等键重试"
        )

    variants = await _load_active_variants(db, product, user.id)
    prepared = build_shopify_product_payload(
        product,
        listing,
        variants,
        app_url=app_url,
    )
    publication = await create_publication(
        db,
        user_id=user.id,
        listing_id=listing.id if listing is not None else None,
        platform="shopify",
        channel_id=str(channel.id),
        idempotency_key=idempotency_key,
    )

    shop_url = (
        f"https://{_channel_domain(channel)}"
        f"/admin/api/{settings.SHOPIFY_API_VERSION}"
    )
    headers = {
        "X-Shopify-Access-Token": decrypt_value(channel.access_token),
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{shop_url}/products.json",
                json={"product": prepared.product},
                headers=headers,
            )
        if response.status_code not in (200, 201):
            publication.status = "failed"
            publication.error = response.text[:500]
            await db.commit()
            raise ShopifyPublishError(
                f"Shopify 发布失败：{response.text[:200]}",
                status_code=502,
            )
    except ShopifyPublishError:
        raise
    except Exception as exc:
        publication.status = "failed"
        publication.error = str(exc)[:500]
        await db.commit()
        raise ShopifyPublishError(
            "Shopify 发布请求失败，请稍后重试",
            status_code=502,
        ) from exc

    shopify_product = response.json().get("product", {})
    if listing is not None:
        listing.status = "published"
        listing.published_at = datetime.now(timezone.utc)
    publication.status = "completed"
    publication.external_product_id = str(shopify_product.get("id") or "")
    publication.external_url = (
        f"https://{_channel_domain(channel)}/admin/products/"
        f"{shopify_product.get('id')}"
    )
    await db.commit()
    return ShopifyPublishResult(
        publication=publication,
        prepared=prepared,
        replayed=False,
    )


def serialize_shopify_publish_result(result: ShopifyPublishResult) -> dict:
    """把统一结果转成网页和 Agent 共用响应。"""
    data = publication_response(result.publication)
    if result.replayed:
        data["message"] = "相同发布请求已完成，返回已有 Shopify 草稿商品"
    else:
        data["message"] = "商品已完整发布到 Shopify（草稿状态）"
    data["variants_published"] = result.prepared.variant_count if result.prepared else None
    data["images_published"] = result.prepared.image_count if result.prepared else None
    data["replayed"] = result.replayed
    return data
