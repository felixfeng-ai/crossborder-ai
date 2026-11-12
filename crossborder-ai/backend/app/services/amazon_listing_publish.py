"""Amazon SP-API Listings Items 预览与发布适配器。"""

import json
from typing import Any
from urllib.parse import quote

import httpx

from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.services.amazon_sp_api import AmazonSpApiService


AMAZON_LISTINGS_BASE_URL = "https://sellingpartnerapi-na.amazon.com"


class AmazonListingPublishError(Exception):
    """Amazon Listing 发布时的真实业务错误。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        issues: list[dict] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.issues = issues or []


def _parse_bullets(raw: str | None) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
        return [
            str(item).strip()
            for item in parsed
            if str(item).strip()
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def _language_tag(language: str | None) -> str:
    value = (language or "en").strip().lower()
    return {
        "en": "en_US",
        "zh": "zh_CN",
        "ja": "ja_JP",
        "de": "de_DE",
        "fr": "fr_FR",
        "es": "es_ES",
    }.get(value, "en_US")


def build_amazon_listing_payload(
    product: Product,
    listing: ListingDraft,
    variant: ProductVariant,
    *,
    product_type: str,
    marketplace_id: str,
    language_tag: str | None = None,
    currency: str = "USD",
    additional_attributes: dict[str, Any] | None = None,
) -> dict:
    """构建 Listings Items API 的商品属性载荷。

    价格只读取启用 SKU 的实际售价，绝不使用供货参考价。Amazon 不同
    product type 的必填属性由预览接口返回，调用方可在补充属性中覆盖。
    """
    if not product_type.strip():
        raise AmazonListingPublishError("Amazon product type 不能为空", status_code=400)
    if not marketplace_id.strip():
        raise AmazonListingPublishError("Amazon Marketplace ID 不能为空", status_code=400)
    if not variant.sku.strip():
        raise AmazonListingPublishError("Amazon Listing 缺少 SKU", status_code=409)
    if variant.price is None or float(variant.price) <= 0:
        raise AmazonListingPublishError(
            f"SKU {variant.sku} 缺少大于 0 的销售价",
            status_code=409,
        )

    locale = language_tag or _language_tag(listing.language)
    attributes: dict[str, Any] = {
        "item_name": [{"value": listing.title, "language_tag": locale}],
        "condition_type": [{"value": "new_new"}],
        "purchasable_offer": [
            {
                "marketplace_id": marketplace_id,
                "currency": currency,
                "audience": "ALL",
                "our_price": [
                    {
                        "schedule": [
                            {
                                "value_with_tax": round(float(variant.price), 2),
                            }
                        ]
                    }
                ],
            }
        ],
        "fulfillment_availability": [
            {
                "fulfillment_channel_code": "DEFAULT",
                "quantity": max(0, int(variant.stock_quantity or 0)),
            }
        ],
    }
    if product.brand_name:
        attributes["brand"] = [{"value": product.brand_name, "language_tag": locale}]
    if listing.description:
        attributes["product_description"] = [
            {"value": listing.description, "language_tag": locale}
        ]
    bullets = _parse_bullets(listing.bullet_points)
    if bullets:
        attributes["bullet_point"] = [
            {"value": item, "language_tag": locale}
            for item in bullets
        ]
    if variant.barcode:
        attributes["externally_assigned_product_identifier"] = [
            {"type": "ean", "value": variant.barcode}
        ]
    if additional_attributes:
        attributes.update(additional_attributes)

    return {
        "productType": product_type.strip().upper(),
        "requirements": "LISTING",
        "attributes": attributes,
    }


class AmazonListingPublishService:
    """调用 SP-API Listings Items API，不伪造提交结果。"""

    async def submit_listing(
        self,
        *,
        refresh_token: str,
        seller_id: str,
        marketplace_id: str,
        sku: str,
        payload: dict,
        preview: bool = False,
    ) -> dict:
        access_token = await AmazonSpApiService().refresh_access_token(refresh_token)
        url = (
            f"{AMAZON_LISTINGS_BASE_URL}/listings/2021-08-01/items/"
            f"{quote(seller_id, safe='')}/{quote(sku, safe='')}"
        )
        params = {"marketplaceIds": marketplace_id}
        if preview:
            params["mode"] = "VALIDATION_PREVIEW"
        headers = {
            "x-amz-access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.put(
                    url,
                    params=params,
                    json=payload,
                    headers=headers,
                )
        except Exception as exc:
            raise AmazonListingPublishError(
                "Amazon Listings Items 请求失败，请稍后重试"
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}
        issues = body.get("issues") if isinstance(body, dict) else None
        if response.status_code in (401, 403):
            raise AmazonListingPublishError(
                "Amazon 应用缺少 Listings Items 权限或授权已失效",
                status_code=403,
                issues=issues if isinstance(issues, list) else [],
            )
        if response.status_code == 429:
            raise AmazonListingPublishError(
                "Amazon API 请求过于频繁，请稍后重试",
                status_code=429,
                issues=issues if isinstance(issues, list) else [],
            )
        if response.status_code >= 400:
            detail = ""
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("errors") or "")
            raise AmazonListingPublishError(
                f"Amazon Listing 提交失败：{detail[:300] or response.text[:300]}",
                status_code=502,
                issues=issues if isinstance(issues, list) else [],
            )
        if not isinstance(body, dict):
            raise AmazonListingPublishError("Amazon 返回了无法解析的响应")
        return body
