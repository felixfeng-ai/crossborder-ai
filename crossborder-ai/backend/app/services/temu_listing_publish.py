"""Temu V3 商品发布请求构建与提交服务。"""

import json
from decimal import Decimal, InvalidOperation
from ipaddress import ip_address
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.services.public_image_storage import (
    PublicImageStorage,
    publish_public_image_asset,
)
from app.services.temu_open_api import (
    TemuOpenApiError,
    TemuOpenApiService,
    normalize_region,
)


def _json_value(value: str | None, expected_type):
    try:
        parsed = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return expected_type()
    return parsed if isinstance(parsed, expected_type) else expected_type()


def _public_https_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(
        (".local", ".test")
    ):
        return False
    try:
        address = ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    )


def _integer(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _price(value: float | None) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Temu SKU 缺少有效销售价") from exc
    if amount <= 0:
        raise ValueError("Temu SKU 缺少有效销售价")
    return format(amount, "f")


def _variations(variant: ProductVariant) -> list[dict]:
    raw = _json_value(variant.attributes_json, dict)
    explicit = raw.get("variations")
    if isinstance(explicit, list):
        rows = []
        for item in explicit:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            value = str(item.get("value") or "").strip()
            if name and value:
                rows.append({"name": name, "value": value})
        return rows
    excluded = {
        "weight",
        "length",
        "width",
        "height",
        "package_info",
        "barcode_type",
    }
    return [
        {"name": str(key), "value": str(value)}
        for key, value in raw.items()
        if str(key) not in excluded and str(value).strip()
    ]


def _package_info(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return None
    keys = ("weight", "length", "width", "height")
    normalized = {
        key: str(value.get(key) or "").strip()
        for key in keys
    }
    if not any(normalized.values()):
        return None
    if not all(normalized.values()):
        raise ValueError("Temu 包装重量和长宽高必须同时提供")
    return normalized


def build_temu_listing_payload(
    product: Product,
    listing: ListingDraft,
    variants: list[ProductVariant],
    *,
    image_urls: list[str],
    category_name: str,
    currency: str,
    language: str,
    attributes: list[dict] | None = None,
    package_info: dict | None = None,
) -> dict:
    """按 V3 契约构建请求，只使用数据库中真实商品字段。"""

    images = [
        str(item).strip()
        for item in image_urls
        if str(item).strip()
    ]
    if not 1 <= len(images) <= 10:
        raise ValueError("Temu 商品必须提供 1 至 10 张公网图片")
    if any(not _public_https_url(item) for item in images):
        raise ValueError("Temu 商品图片必须是公网 HTTPS URL")
    category = str(category_name or "").strip()
    if not category:
        raise ValueError("Temu 商品类目名称不能为空")
    currency_code = str(currency or "").strip().upper()
    if not currency_code:
        raise ValueError("Temu 商品币种不能为空")
    active_variants = [
        item for item in variants if item.is_active
    ]
    if not active_variants:
        raise ValueError("Temu 商品缺少可发布 SKU")
    package = _package_info(package_info)
    normalized_attributes = []
    for item in attributes or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        raw_values = item.get("value")
        if not isinstance(raw_values, list):
            raw_values = [raw_values]
        values = [
            str(value).strip()
            for value in raw_values
            if str(value).strip()
        ]
        if name and values:
            normalized_attributes.append(
                {"name": name, "value": values}
            )
    sku_list = []
    for variant in active_variants:
        external_sku_id = str(variant.sku or "").strip()
        if not external_sku_id:
            raise ValueError("Temu SKU 编码不能为空")
        sku = {
            "externalSkuId": external_sku_id,
            "images": [images[0]],
            "price": {
                "basePrice": {
                    "amount": _price(variant.price),
                    "currency": currency_code,
                }
            },
            "quantity": max(0, int(variant.stock_quantity or 0)),
        }
        variations = _variations(variant)
        if variations:
            sku["variations"] = variations
        if package is not None:
            sku["packageInfo"] = package
        sku_list.append(sku)
    bullet_points = _json_value(listing.bullet_points, list)
    goods_basic = {
        "externalGoodsId": str(product.id),
        "goodsName": str(listing.title or "").strip(),
        "goodsDesc": str(
            listing.description or product.description or ""
        ).strip(),
        "extCatName": category,
        "goodsCarouselImage": images,
        "detailImage": images,
        "productType": 1,
    }
    if bullet_points:
        goods_basic["bulletPoints"] = [
            str(item).strip()
            for item in bullet_points
            if str(item).strip()
        ]
    if product.lead_time_days and product.lead_time_days > 0:
        goods_basic["shipmentLimitDay"] = int(product.lead_time_days)
    return {
        "language": str(language or listing.language or "en"),
        "goodsBasic": goods_basic,
        "attributes": normalized_attributes,
        "skuList": sku_list,
    }


class TemuListingPublishService:
    """执行 Temu V3 创建和商品回读。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        open_api: TemuOpenApiService | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.open_api = open_api or TemuOpenApiService()

    async def publish_asset(
        self,
        asset: ImageAsset,
        *,
        storage: PublicImageStorage,
    ) -> str:
        return await publish_public_image_asset(
            asset,
            storage=storage,
        )

    async def _connection(self, connection_id: UUID) -> PlatformConnection:
        connection = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.id == connection_id,
                    PlatformConnection.user_id == self.user_id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            raise ValueError("Temu 店铺不存在或授权不可用")
        return connection

    def _authorize(
        self,
        connection: PlatformConnection,
        *,
        required_scopes: set[str] | None = None,
    ) -> tuple[dict, str]:
        try:
            metadata = json.loads(connection.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        store_type = str(metadata.get("store_type") or "").strip().lower()
        if store_type not in {"local", "semi"}:
            raise ValueError("Temu 商品发布只支持 LOCAL/SEMI 店铺")
        scopes = {
            str(item).strip()
            for item in metadata.get("api_scope_list") or []
            if str(item).strip()
        }
        missing = (
            required_scopes
            or {
                "temu.local.goods.v3.add",
                "bg.local.goods.list.query",
            }
        ) - scopes
        if missing:
            raise ValueError(
                "Temu 商品发布 scope 不完整："
                + "、".join(sorted(missing))
            )
        try:
            credentials = json.loads(decrypt_value(connection.credentials))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Temu 店铺授权内容无效") from exc
        access_token = str(
            credentials.get("access_token") or ""
        ).strip()
        if not access_token:
            raise ValueError("Temu 店铺授权缺少 Access Token")
        return metadata, access_token

    async def _request(
        self,
        *,
        connection_id: UUID,
        api_type: str,
        request_data: dict,
        required_scopes: set[str] | None = None,
    ) -> dict:
        connection = await self._connection(connection_id)
        _metadata, access_token = self._authorize(
            connection,
            required_scopes=required_scopes,
        )
        body = await self.open_api.request(
            api_type=api_type,
            access_token=access_token,
            region=normalize_region(connection.marketplace_id or "global"),
            request_data=request_data,
        )
        result = body.get("result")
        return result if isinstance(result, dict) else {}

    async def submit(
        self,
        *,
        connection_id: UUID,
        payload: dict,
    ) -> dict:
        result = await self._request(
            connection_id=connection_id,
            api_type="temu.local.goods.v3.add",
            request_data=payload,
            required_scopes={
                "temu.local.goods.v3.add",
                "bg.local.goods.list.query",
            },
        )
        goods_id = result.get("goodsId")
        external_goods_id = str(
            result.get("externalGoodsId") or ""
        ).strip()
        if goods_id in (None, "", 0):
            raise ValueError("Temu 商品创建未返回 goodsId")
        return {
            "goods_id": int(goods_id),
            "external_goods_id": external_goods_id,
        }

    async def read_product(
        self,
        *,
        connection_id: UUID,
        goods_id: int,
    ) -> dict | None:
        result = await self._request(
            connection_id=connection_id,
            api_type="bg.local.goods.list.query",
            request_data={
                "pageNo": 1,
                "pageSize": 20,
                "goodsIdList": [int(goods_id)],
            },
            required_scopes={"bg.local.goods.list.query"},
        )
        rows = result.get("goodsList")
        if not isinstance(rows, list):
            rows = result.get("pageItems")
        if not isinstance(rows, list):
            return None
        row = next(
            (
                item
                for item in rows
                if isinstance(item, dict)
                and _integer(item.get("goodsId")) == int(goods_id)
            ),
            None,
        )
        if row is None:
            return None
        return {
            "goods_id": _integer(row.get("goodsId"), goods_id),
            "external_goods_id": str(
                row.get("outGoodsSn")
                or row.get("externalGoodsId")
                or ""
            ),
            "status": row.get("status4VO", row.get("status")),
            "sub_status": row.get(
                "subStatus4VO",
                row.get("subStatus"),
            ),
        }

    async def get_publish_statuses(
        self,
        *,
        connection_id: UUID,
        goods_ids: list[int],
    ) -> list[dict]:
        """批量读取 Temu 商品发布原始状态。"""

        ids = sorted(
            {
                int(item)
                for item in goods_ids
                if int(item) > 0
            }
        )
        if not ids:
            return []
        try:
            result = await self._request(
                connection_id=connection_id,
                api_type="bg.local.goods.publish.status.get",
                request_data={"goodsIdList": ids[:100]},
                required_scopes={
                    "bg.local.goods.publish.status.get",
                    "bg.local.goods.list.query",
                },
            )
        except TemuOpenApiError as exc:
            if exc.error_code == 4000004:
                raise
            result = None
        except ValueError:
            # 没有状态 scope 或状态接口暂不可用时，按商品列表回读原始码。
            result = None
        if result is None:
            fallback = []
            for goods_id in ids:
                remote = await self.read_product(
                    connection_id=connection_id,
                    goods_id=goods_id,
                )
                if remote is None:
                    continue
                fallback.append(
                    {
                        "goods_id": goods_id,
                        "status": remote.get("status"),
                        "sub_status": remote.get("sub_status"),
                    }
                )
            return fallback
        rows = result.get("goodsPublishStatusList")
        if not isinstance(rows, list):
            return []
        normalized = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            goods_id = _integer(item.get("goodsId"))
            if goods_id <= 0:
                continue
            normalized.append(
                {
                    "goods_id": goods_id,
                    "status": item.get("status"),
                    "sub_status": item.get("subStatus"),
                }
            )
        return normalized
