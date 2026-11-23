"""Temu LOCAL/SEMI 订单只读与业务字段归一化。"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.platform_connection import PlatformConnection
from app.services.temu_capabilities import derive_temu_capabilities
from app.services.temu_open_api import TemuOpenApiService, normalize_region


class TemuOrderReadService:
    """只允许 LOCAL/SEMI 店铺读取订单，拒绝跨境接口猜测。"""

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
        store_type = str(metadata.get("store_type") or "unknown").lower()
        if store_type not in {"local", "semi"}:
            raise ValueError(
                "Temu 店铺类型限制：bg.order.list.v2.get 仅支持 LOCAL/SEMI 店铺"
            )
        capabilities = derive_temu_capabilities(
            metadata.get("api_scope_list") or [],
            store_type=store_type,
        )
        order_read = capabilities["order.read"]
        if not order_read["available"]:
            raise ValueError("当前 Temu 店铺没有订单读取权限")
        if "bg.order.list.v2.get" not in order_read["scopes"]:
            raise ValueError("首发只支持 bg.order.list.v2.get 订单读取接口")
        credentials = json.loads(decrypt_value(connection.credentials))
        access_token = str(
            credentials.get("access_token") or ""
        ).strip()
        if not access_token:
            raise ValueError("Temu 店铺授权缺少 Access Token")
        return metadata, access_token

    def _labels(self, values) -> list[dict]:
        return [
            {
                "name": str(item.get("name") or ""),
                "value": item.get("value"),
            }
            for item in values or []
            if isinstance(item, dict)
        ]

    def _normalize_item(self, item: dict) -> dict:
        parent = item.get("parentOrderMap") or {}
        orders = []
        for order in item.get("orderList") or []:
            if not isinstance(order, dict):
                continue
            orders.append(
                {
                    "order_sn": str(order.get("orderSn") or ""),
                    "order_status": order.get("orderStatus"),
                    "goods_id": str(order.get("goodsId") or ""),
                    "goods_name": str(order.get("goodsName") or ""),
                    "sku_id": str(order.get("skuId") or ""),
                    "quantity": int(order.get("quantity") or 0),
                    "spec": str(order.get("spec") or ""),
                    "fulfillment_type": str(
                        order.get("fulfillmentType") or ""
                    ),
                    "package_abnormal_types": [
                        str(value)
                        for value in order.get("packageAbnormalTypeList")
                        or []
                    ],
                    "created_time": order.get("orderCreateTime"),
                    "shipping_time": order.get("orderShippingTime"),
                    "inventory_warehouse_id": str(
                        order.get("inventoryDeductionWarehouseId") or ""
                    ),
                    "inventory_warehouse_name": str(
                        order.get("inventoryDeductionWarehouseName") or ""
                    ),
                }
            )
        paid_shipping = parent.get("buyerPaidShippingAmount") or {}
        return {
            "parent_order_sn": str(parent.get("parentOrderSn") or ""),
            "parent_order_status": parent.get("parentOrderStatus"),
            "created_time": parent.get("parentOrderTime"),
            "updated_time": parent.get("updateTime"),
            "expect_ship_latest_time": parent.get("expectShipLatestTime"),
            "fulfillment_warnings": [
                str(value)
                for value in parent.get("fulfillmentWarning") or []
            ],
            "labels": self._labels(parent.get("parentOrderLabel")),
            "paid_shipping_amount": (
                {
                    "amount": paid_shipping.get("amount"),
                    "currency": str(paid_shipping.get("currency") or ""),
                }
                if isinstance(paid_shipping, dict)
                else {}
            ),
            "orders": orders,
        }

    async def list_orders(
        self,
        *,
        connection_id: UUID,
        page_number: int = 1,
        page_size: int = 20,
        parent_order_status: int | None = None,
    ) -> dict:
        connection = await self._connection(connection_id)
        metadata, access_token = self._authorize(connection)
        page_number = max(1, int(page_number))
        page_size = max(1, min(int(page_size), 100))
        request_data = {
            "pageNumber": page_number,
            "pageSize": page_size,
        }
        if parent_order_status is not None:
            request_data["parentOrderStatus"] = int(parent_order_status)
        body = await self.open_api.request(
            api_type="bg.order.list.v2.get",
            access_token=access_token,
            region=normalize_region(connection.marketplace_id or "global"),
            request_data=request_data,
        )
        result = body.get("result") or {}
        items = result.get("pageItems") or []
        if not isinstance(items, list):
            items = []
        return {
            "connection_id": str(connection.id),
            "external_account_id": connection.external_account_id,
            "store_type": metadata.get("store_type") or "unknown",
            "page_number": page_number,
            "total": int(result.get("totalItemNum") or 0),
            "items": [
                self._normalize_item(item)
                for item in items
                if isinstance(item, dict)
            ],
        }
