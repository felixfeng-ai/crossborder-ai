"""Temu LOCAL/SEMI 库存查询与全量覆写服务。"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.platform_connection import PlatformConnection
from app.services.temu_open_api import TemuOpenApiService, normalize_region


REQUIRED_INVENTORY_SCOPES = {
    "temu.goods.stock.query",
    "bg.local.goods.stock.edit",
}
MAX_STOCK_TARGET = 1_000_000


def build_temu_stock_payload(
    *,
    goods_id: int,
    sku_id: int,
    stock_target: int,
    request_unique_key: str,
) -> dict:
    """构建全量目标库存请求，避免重试时重复应用增量。"""

    if int(goods_id) <= 0:
        raise ValueError("Temu goodsId 必须大于 0")
    if int(sku_id) <= 0:
        raise ValueError("Temu skuId 必须大于 0")
    target = int(stock_target)
    if target < 0 or target > MAX_STOCK_TARGET:
        raise ValueError("Temu 库存必须在 0 至 1000000 之间")
    key = str(request_unique_key or "").strip()
    if not key:
        raise ValueError("Temu 库存请求缺少幂等键")
    return {
        "request": {
            "goodsId": int(goods_id),
            "stockType": 0,
            "skuStockTargetList": [
                {
                    "skuId": int(sku_id),
                    "stockTarget": target,
                }
            ],
            "requestUniqueKey": key,
        }
    }


class TemuInventoryService:
    """读取并覆写 Temu 普通库存。"""

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

    def _authorize(self, connection: PlatformConnection) -> str:
        try:
            metadata = json.loads(connection.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        store_type = str(metadata.get("store_type") or "").strip().lower()
        if store_type not in {"local", "semi"}:
            raise ValueError("Temu 库存动作只支持 LOCAL/SEMI 店铺")
        scopes = {
            str(item).strip()
            for item in metadata.get("api_scope_list") or []
            if str(item).strip()
        }
        missing = REQUIRED_INVENTORY_SCOPES - scopes
        if missing:
            raise ValueError(
                "Temu 库存 scope 不完整：" + "、".join(sorted(missing))
            )
        try:
            credentials = json.loads(decrypt_value(connection.credentials))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Temu 店铺授权内容无效") from exc
        token = str(credentials.get("access_token") or "").strip()
        if not token:
            raise ValueError("Temu 店铺授权缺少 Access Token")
        return token

    async def _body(
        self,
        *,
        connection_id: UUID,
        api_type: str,
        request_data: dict,
    ) -> dict:
        connection = await self._connection(connection_id)
        token = self._authorize(connection)
        return await self.open_api.request(
            api_type=api_type,
            access_token=token,
            region=normalize_region(connection.marketplace_id or "global"),
            request_data=request_data,
        )

    async def _request(
        self,
        *,
        connection_id: UUID,
        api_type: str,
        request_data: dict,
    ) -> dict:
        body = await self._body(
            connection_id=connection_id,
            api_type=api_type,
            request_data=request_data,
        )
        result = body.get("result")
        return result if isinstance(result, dict) else {}

    async def get_stock(
        self,
        *,
        connection_id: UUID,
        goods_id: int,
        out_sku_sns: list[str],
    ) -> dict | None:
        result = await self._request(
            connection_id=connection_id,
            api_type="temu.goods.stock.query",
            request_data={
                "goodsId": int(goods_id),
                "outSkuSnList": list(out_sku_sns),
            },
        )
        rows = result.get("stockList")
        if not isinstance(rows, list):
            return None
        goods = next(
            (
                item
                for item in rows
                if isinstance(item, dict)
                and int(item.get("goodsId") or 0) == int(goods_id)
            ),
            None,
        )
        if goods is None:
            return None
        skus = []
        for item in goods.get("skuStockInfoList") or []:
            if not isinstance(item, dict):
                continue
            ordinary = item.get("selfOrdinaryStock") or {}
            sku_id = int(item.get("skuId") or 0)
            if sku_id <= 0:
                continue
            skus.append(
                {
                    "sku_id": sku_id,
                    "out_sku_sn": str(item.get("outSkuSn") or ""),
                    "stock": max(
                        0,
                        int(ordinary.get("stock") or 0),
                    ),
                }
            )
        return {
            "goods_id": int(goods_id),
            "skus": skus,
        }

    async def update_stock(
        self,
        *,
        connection_id: UUID,
        goods_id: int,
        sku_id: int,
        stock_target: int,
        request_unique_key: str,
    ) -> dict:
        payload = build_temu_stock_payload(
            goods_id=goods_id,
            sku_id=sku_id,
            stock_target=stock_target,
            request_unique_key=request_unique_key,
        )
        body = await self._body(
            connection_id=connection_id,
            api_type="bg.local.goods.stock.edit",
            request_data=payload,
        )
        result = body.get("result")
        result = result if isinstance(result, dict) else {}
        if "operateResult" in body:
            # 官方库存编辑响应把操作结果放在顶层，不使用 result 包裹。
            result = body
        statuses = [
            item
            for item in result.get("skuStockEditStatusInfoList") or []
            if isinstance(item, dict)
        ]
        succeeded = bool(result.get("operateResult"))
        if not succeeded:
            reasons = [
                str(item.get("errorMsg") or "").strip()
                for item in statuses
                if not item.get("stockEditStatus")
                and str(item.get("errorMsg") or "").strip()
            ]
            raise ValueError(
                "Temu 库存更新失败"
                + (f"：{'；'.join(reasons)}" if reasons else "")
            )
        return {
            "goods_id": int(result.get("goodsId") or goods_id),
            "sku_id": int(sku_id),
            "stock_target": int(stock_target),
            "succeeded": True,
        }
