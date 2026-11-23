"""Temu 商品只读服务与业务字段归一化。"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.platform_connection import PlatformConnection
from app.services.temu_capabilities import derive_temu_capabilities
from app.services.temu_open_api import TemuOpenApiService, normalize_region


class TemuProductReadService:
    """仅在 scope 和店铺类型匹配时读取 Temu 商品列表。"""

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

    def _metadata(self, connection: PlatformConnection) -> dict:
        try:
            metadata = json.loads(connection.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        return metadata if isinstance(metadata, dict) else {}

    def _authorize(self, connection: PlatformConnection) -> tuple[dict, str]:
        metadata = self._metadata(connection)
        scopes = metadata.get("api_scope_list") or []
        capabilities = derive_temu_capabilities(
            scopes,
            store_type=metadata.get("store_type"),
        )
        product_read = capabilities["product.read"]
        if not product_read["available"]:
            raise ValueError("当前 Temu 店铺没有商品读取权限")
        if product_read["restriction_required"]:
            raise ValueError(f"Temu 店铺类型限制：{product_read['reason']}")
        if "bg.local.goods.list.query" not in product_read["scopes"]:
            raise ValueError("首发只支持 bg.local.goods.list.query 商品读取接口")
        credentials = json.loads(decrypt_value(connection.credentials))
        access_token = str(
            credentials.get("access_token") or ""
        ).strip()
        if not access_token:
            raise ValueError("Temu 店铺授权缺少 Access Token")
        return metadata, access_token

    def _normalize_goods(self, goods: dict) -> dict:
        retail_price = goods.get("retailPrice") or {}
        list_price = goods.get("listPrice") or {}
        skus = []
        for sku in goods.get("skuInfoList") or []:
            if not isinstance(sku, dict):
                continue
            specs = [
                {
                    "parent_spec_name": str(item.get("parentSpecName") or ""),
                    "spec_name": str(item.get("specName") or ""),
                }
                for item in sku.get("specList") or []
                if isinstance(item, dict)
            ]
            skus.append(
                {
                    "sku_id": str(sku.get("skuId") or ""),
                    "sku_sn": str(sku.get("skuSn") or ""),
                    "stock": int(sku.get("stock") or 0),
                    "specs": specs,
                }
            )
        return {
            "goods_id": str(goods.get("goodsId") or ""),
            "external_goods_sn": str(goods.get("outGoodsSn") or ""),
            "name": str(goods.get("goodsName") or ""),
            "status": goods.get("status4VO"),
            "sub_status": goods.get("subStatus4VO"),
            "status_changed_at": str(
                goods.get("goodsStatusChangeTime") or ""
            ),
            "price": str(goods.get("price") or ""),
            "market_price": goods.get("marketPrice"),
            "currency": str(goods.get("currency") or ""),
            "retail_price": (
                {
                    "amount": str(retail_price.get("amount") or ""),
                    "currency": str(retail_price.get("currency") or ""),
                }
                if isinstance(retail_price, dict)
                else {}
            ),
            "list_price": (
                {
                    "amount": str(list_price.get("amount") or ""),
                    "currency": str(list_price.get("currency") or ""),
                }
                if isinstance(list_price, dict)
                else {}
            ),
            "thumbnail_url": str(goods.get("thumbUrl") or ""),
            "skus": skus,
        }

    async def list_products(
        self,
        *,
        connection_id: UUID,
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict:
        connection = await self._connection(connection_id)
        metadata, access_token = self._authorize(connection)
        page_no = max(1, int(page_no))
        page_size = max(1, min(int(page_size), 50))
        region = normalize_region(connection.marketplace_id or "global")
        body = await self.open_api.request(
            api_type="bg.local.goods.list.query",
            access_token=access_token,
            region=region,
            request_data={
                "pageNo": page_no,
                "pageSize": page_size,
            },
        )
        result = body.get("result") or {}
        goods_list = result.get("goodsList") or []
        if not isinstance(goods_list, list):
            goods_list = []
        return {
            "connection_id": str(connection.id),
            "external_account_id": connection.external_account_id,
            "region": region,
            "store_type": metadata.get("store_type") or "unknown",
            "page_no": int(result.get("pageNo") or page_no),
            "total": int(result.get("total") or 0),
            "items": [
                self._normalize_goods(item)
                for item in goods_list
                if isinstance(item, dict)
            ],
        }
