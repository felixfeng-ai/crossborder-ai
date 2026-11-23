"""Temu LOCAL/SEMI 供货价变更提交服务。"""

import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.platform_connection import PlatformConnection
from app.services.temu_open_api import (
    TemuOpenApiError,
    TemuOpenApiService,
    normalize_region,
)


REQUIRED_PRICE_SCOPES = {
    "bg.local.goods.list.query",
    "bg.local.goods.priceorder.query",
    "bg.local.goods.priceorder.change.sku.price",
}
MODIFIABLE_PRICE_STATUSES = {201, 202, 203, 205, 206}


def _price_error(exc: TemuOpenApiError) -> str:
    messages = {
        3000021: "Temu 应用没有价格接口白名单权限",
        3000027: "Temu 应用没有价格接口白名单权限",
        3000032: "Temu 店铺未授权价格接口",
        150011103: "Temu 还有待确认价格，请先在卖家中心确认",
        150011101: "本次涨跌幅超过 Temu 允许范围，请分步调整",
        150010233: "商品在促销或冷却期，当前不能降价",
        150019004: "价格超出 Temu 对该 SKU 的可接受范围",
    }
    return messages.get(exc.error_code, str(exc))


def _amount(value: str | Decimal | int | float) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Temu 新供货价格式不正确") from exc
    if amount <= 0:
        raise ValueError("Temu 新供货价必须大于 0")
    return format(amount, "f")


def build_temu_price_change_payload(
    *,
    goods_id: int,
    sku_id: int,
    amount: str,
    currency: str,
    reason: str,
) -> dict:
    """构建单个 SKU 的基础供货价变更请求。"""

    if int(goods_id) <= 0:
        raise ValueError("Temu goodsId 必须大于 0")
    if int(sku_id) <= 0:
        raise ValueError("Temu skuId 必须大于 0")
    currency_code = str(currency or "").strip().upper()
    if not currency_code:
        raise ValueError("Temu 新供货价币种不能为空")
    change_reason = str(reason or "").strip()
    if not change_reason:
        raise ValueError("Temu 价格变更原因不能为空")
    return {
        "goodsId": int(goods_id),
        "changeSkuPriceDTOList": [
            {
                "reason": change_reason,
                "skuChangePriceBaseDTOList": [
                    {
                        "skuId": int(sku_id),
                        "newSupplierPrice": {
                            "amount": _amount(amount),
                            "currency": currency_code,
                        },
                    }
                ],
            }
        ],
    }


class TemuPriceService:
    """读取 SKU/审核流程并提交基础供货价变更。"""

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
            raise ValueError("Temu 价格动作只支持 LOCAL/SEMI 店铺")
        scopes = {
            str(item).strip()
            for item in metadata.get("api_scope_list") or []
            if str(item).strip()
        }
        missing = REQUIRED_PRICE_SCOPES - scopes
        if missing:
            raise ValueError(
                "Temu 价格 scope 不完整：" + "、".join(sorted(missing))
            )
        try:
            credentials = json.loads(decrypt_value(connection.credentials))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Temu 店铺授权内容无效") from exc
        token = str(credentials.get("access_token") or "").strip()
        if not token:
            raise ValueError("Temu 店铺授权缺少 Access Token")
        return token

    async def _request(
        self,
        *,
        connection_id: UUID,
        api_type: str,
        request_data: dict,
    ) -> dict:
        connection = await self._connection(connection_id)
        token = self._authorize(connection)
        body = await self.open_api.request(
            api_type=api_type,
            access_token=token,
            region=normalize_region(connection.marketplace_id or "global"),
            request_data=request_data,
        )
        result = body.get("result")
        return result if isinstance(result, dict) else {}

    async def get_product_sku(
        self,
        *,
        connection_id: UUID,
        goods_id: int,
        out_sku_sn: str,
    ) -> dict | None:
        result = await self._request(
            connection_id=connection_id,
            api_type="bg.local.goods.list.query",
            request_data={
                "pageNo": 1,
                "pageSize": 20,
                "goodsIdList": [int(goods_id)],
            },
        )
        rows = result.get("goodsList")
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
        matches = []
        for item in goods.get("skuInfoList") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("skuSn") or "").strip() != out_sku_sn:
                continue
            sku_id = int(item.get("skuId") or 0)
            if sku_id > 0:
                matches.append(sku_id)
        if not matches:
            raise ValueError("Temu 商品中找不到对应外部 SKU")
        if len(set(matches)) > 1:
            raise ValueError("Temu 外部 SKU 映射不唯一，拒绝猜测价格")
        return {
            "goods_id": int(goods_id),
            "sku_id": matches[0],
            "out_sku_sn": out_sku_sn,
        }

    async def get_price_workflow(
        self,
        *,
        connection_id: UUID,
        goods_id: int,
    ) -> dict:
        result = await self._request(
            connection_id=connection_id,
            api_type="bg.local.goods.priceorder.query",
            request_data={
                "goodsId": str(goods_id),
                "priceOrderType": 2,
                "page": 1,
                "size": 10,
            },
        )
        rows = result.get("priceAuditList")
        rows = rows if isinstance(rows, list) else []
        audit_orders = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            audit_orders.append(
                {
                    "order_id": str(
                        item.get("orderId")
                        or item.get("priceOrderId")
                        or ""
                    ),
                    "status": item.get("status"),
                    "raw": {
                        key: item.get(key)
                        for key in (
                            "orderId",
                            "priceOrderId",
                            "status",
                            "createTime",
                            "updateTime",
                        )
                        if key in item
                    },
                }
            )
        blocked = [
            item
            for item in audit_orders
            if item["status"] is not None
            and int(item["status"]) not in MODIFIABLE_PRICE_STATUSES
        ]
        return {
            "goods_id": int(goods_id),
            "price_audit_list": audit_orders,
            "allows_change": not blocked,
            "blocked_orders": blocked,
        }

    async def submit_price_change(
        self,
        *,
        connection_id: UUID,
        goods_id: int,
        sku_id: int,
        amount: str,
        currency: str,
        reason: str,
    ) -> dict:
        payload = build_temu_price_change_payload(
            goods_id=goods_id,
            sku_id=sku_id,
            amount=amount,
            currency=currency,
            reason=reason,
        )
        try:
            await self._request(
                connection_id=connection_id,
                api_type="bg.local.goods.priceorder.change.sku.price",
                request_data=payload,
            )
        except TemuOpenApiError as exc:
            raise ValueError(_price_error(exc)) from exc
        return {
            "goods_id": int(goods_id),
            "sku_id": int(sku_id),
            "amount": _amount(amount),
            "currency": str(currency).strip().upper(),
            "accepted": True,
        }
