"""Temu LOCAL/SEMI 自履约订单、承运商与物流回读服务。"""

import json
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


REQUIRED_FULFILLMENT_SCOPES = {
    "bg.order.detail.v2.get",
    "bg.logistics.companies.get",
    "bg.logistics.shipment.v2.confirm",
    "bg.logistics.shipment.v2.get",
}


def _int_value(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _confirmation_error(exc: TemuOpenApiError) -> str:
    """把常见发货拒绝码转换为卖家可执行的提示。"""

    messages = {
        120014001: "Temu 未收到物流单号",
        120014020: "物流单号包含 Temu 不支持的符号",
        120014005: "Temu 不识别该承运商下的物流单号",
        120014008: "Temu 不识别该承运商下的物流单号",
        120014023: "Temu 不识别该承运商下的物流单号",
        120014022: "物流单号与承运商不匹配",
        120014019: "Temu 生成的物流单号不能用于自发货确认",
        120012023: "买家正在申请改地址，请先处理改地址请求",
        120012030: "买家正在申请取消，请先处理取消请求",
        120011065: "Temu 订单还没有可用收货地址",
        120012035: "该店铺不能使用自发货确认，必须走 Temu 面单流程",
        120012076: "该店铺不能使用自发货确认，必须走 Temu 面单流程",
        120011085: "Temu 自发货仓库缺失或不正确",
        120012063: "Temu 自发货仓库缺失或不正确",
        120012064: "Temu 自发货仓库缺失或不正确",
        120011086: "请先在 Temu 卖家中心补全仓库类型和品牌",
        120015537: "巴西订单只能使用 Temu 自有面单",
    }
    return messages.get(exc.error_code, str(exc))


class TemuFulfillmentService:
    """封装自履约所需的四个官方接口和字段白名单。"""

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

    def _authorize(self, connection: PlatformConnection) -> tuple[dict, str]:
        try:
            metadata = json.loads(connection.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        store_type = str(metadata.get("store_type") or "").strip().lower()
        if store_type not in {"local", "semi"}:
            raise ValueError("Temu 自发货只支持 LOCAL/SEMI 店铺")
        scopes = {
            str(item).strip()
            for item in metadata.get("api_scope_list") or []
            if str(item).strip()
        }
        missing = sorted(REQUIRED_FULFILLMENT_SCOPES - scopes)
        if missing:
            raise ValueError(
                "Temu 自发货 scope 不完整：" + "、".join(missing)
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
    ) -> dict | list:
        connection = await self._connection(connection_id)
        _metadata, access_token = self._authorize(connection)
        body = await self.open_api.request(
            api_type=api_type,
            access_token=access_token,
            region=normalize_region(connection.marketplace_id or "global"),
            request_data=request_data,
        )
        result = body.get("result")
        return result if isinstance(result, (dict, list)) else {}

    async def get_order_detail(
        self,
        *,
        connection_id: UUID,
        parent_order_sn: str,
    ) -> dict:
        """读取父订单并只保留履约所需字段。"""

        result = await self._request(
            connection_id=connection_id,
            api_type="bg.order.detail.v2.get",
            request_data={"parentOrderSn": parent_order_sn},
        )
        if not isinstance(result, dict):
            result = {}
        parent = result.get("parentOrderMap")
        parent = parent if isinstance(parent, dict) else {}
        raw_lines = result.get("orderList")
        raw_lines = raw_lines if isinstance(raw_lines, list) else []
        lines = []
        for item in raw_lines:
            if not isinstance(item, dict):
                continue
            lines.append(
                {
                    "order_sn": str(item.get("orderSn") or "").strip(),
                    "goods_id": _int_value(item.get("goodsId")),
                    "sku_id": _int_value(item.get("skuId")),
                    "quantity": max(
                        0,
                        _int_value(item.get("quantity")),
                    ),
                    "fulfillment_type": str(
                        item.get("fulfillmentType") or ""
                    ).strip(),
                    "order_status": item.get("orderStatus"),
                    "shipping_time": _int_value(
                        item.get("orderShippingTime")
                    ),
                    "is_cancelled_during_pending": bool(
                        item.get("isCancelledDuringPending")
                    ),
                }
            )
        active_lines = [
            item
            for item in lines
            if not item["is_cancelled_during_pending"]
            and item["quantity"] > 0
        ]
        return {
            "connection_id": str(connection_id),
            "external_account_id": str(
                (await self._connection(connection_id)).external_account_id
            ),
            "parent_order_sn": str(
                parent.get("parentOrderSn") or parent_order_sn
            ),
            "region_id": _int_value(parent.get("regionId")),
            "parent_shipping_time": _int_value(
                parent.get("parentShippingTime")
            ),
            "lines": lines,
            "active_lines": active_lines,
            "item_count": sum(item["quantity"] for item in active_lines),
            "shipped": bool(lines)
            and all(item["shipping_time"] > 0 for item in lines),
        }

    async def list_carriers(
        self,
        *,
        connection_id: UUID,
        region_id: int,
    ) -> list[dict]:
        result = await self._request(
            connection_id=connection_id,
            api_type="bg.logistics.companies.get",
            request_data={"regionId": int(region_id)},
        )
        if isinstance(result, list):
            source = result
        elif isinstance(result, dict):
            rows = result.get("result")
            source = rows if isinstance(rows, list) else [result]
        else:
            source = []
        carriers = []
        for item in source:
            if not isinstance(item, dict):
                continue
            carrier_id = _int_value(
                item.get("logisticsServiceProviderId")
            )
            if carrier_id <= 0:
                continue
            carriers.append(
                {
                    "carrier_id": carrier_id,
                    "name": str(
                        item.get("logisticsServiceProviderName")
                        or item.get("logisticsBrandName")
                        or carrier_id
                    ),
                }
            )
        return carriers

    async def confirm_shipment(
        self,
        *,
        connection_id: UUID,
        payload: dict,
    ) -> dict:
        try:
            result = await self._request(
                connection_id=connection_id,
                api_type="bg.logistics.shipment.v2.confirm",
                request_data=payload,
            )
        except TemuOpenApiError as exc:
            if exc.error_code == 120012004:
                return {
                    "warnings": [],
                    "already_shipped": True,
                }
            raise ValueError(_confirmation_error(exc)) from exc
        if not isinstance(result, dict):
            result = {}
        return {
            "warnings": [
                str(value)
                for value in result.get("warningMessage") or []
            ],
        }

    @staticmethod
    def _tracking_numbers(value) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "trackingNumber" and item not in (None, ""):
                    found.add(str(item).strip())
                else:
                    found.update(
                        TemuFulfillmentService._tracking_numbers(item)
                    )
        elif isinstance(value, list):
            for item in value:
                found.update(
                    TemuFulfillmentService._tracking_numbers(item)
                )
        return found

    async def get_shipment(
        self,
        *,
        connection_id: UUID,
        parent_order_sn: str,
        order_sn: str,
    ) -> dict:
        result = await self._request(
            connection_id=connection_id,
            api_type="bg.logistics.shipment.v2.get",
            request_data={
                "parentOrderSn": parent_order_sn,
                "orderSn": order_sn,
            },
        )
        if not isinstance(result, dict):
            result = {}
        rows = result.get("shipmentInfoDTO")
        rows = rows if isinstance(rows, list) else []
        return {
            "order_sn": order_sn,
            "tracking_numbers": sorted(
                self._tracking_numbers(rows)
            ),
        }
