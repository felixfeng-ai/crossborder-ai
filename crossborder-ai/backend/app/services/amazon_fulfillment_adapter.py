"""Amazon FBM 确认发货动作适配器。"""

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.platform_connection import PlatformConnection
from app.models.workspace import Workspace
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.amazon_orders import AmazonOrdersService
from app.services.amazon_sp_api import AmazonSpApiService


AMAZON_ORDER_ID_PATTERN = re.compile(r"^\d{3}-\d{7}-\d{7}$")


def _time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class AmazonOrderFulfillmentActionAdapter:
    """准备并提交 Amazon 商户自履约订单发货确认。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        service: AmazonOrdersService | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.service = service or AmazonOrdersService()

    async def _connection(self, marketplace_id: str) -> PlatformConnection:
        workspace = await self.db.get(Workspace, self.workspace_id)
        if workspace is None:
            raise ValueError("工作区不存在")
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id.in_(
                        {self.user_id, workspace.owner_user_id}
                    ),
                    PlatformConnection.platform == "amazon",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection = next(
            (
                item
                for item in connections
                if item.marketplace_id == marketplace_id
            ),
            None,
        )
        if connection is None:
            raise ValueError("当前工作区未绑定该 Amazon Marketplace")
        return connection

    def _refresh_token(self, connection: PlatformConnection) -> str:
        try:
            credentials = json.loads(
                decrypt_value(connection.credentials)
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Amazon 店铺授权内容无效") from exc
        refresh_token = str(
            credentials.get("refresh_token") or ""
        ).strip()
        if not refresh_token:
            raise ValueError("Amazon 店铺授权缺少 Refresh Token")
        return refresh_token

    def _input_values(self, input_data: dict) -> dict:
        marketplace_id = str(
            input_data.get("marketplace_id") or ""
        ).strip()
        carrier_code = str(
            input_data.get("carrier_code") or ""
        ).strip()
        carrier_name = str(
            input_data.get("carrier_name") or ""
        ).strip()
        tracking_number = str(
            input_data.get("tracking_number") or ""
        ).strip()
        shipping_method = str(
            input_data.get("shipping_method") or ""
        ).strip()
        package_reference_id = str(
            input_data.get("package_reference_id") or "1"
        ).strip()
        if not marketplace_id:
            raise ValueError("Amazon Marketplace ID 不能为空")
        if not carrier_code:
            raise ValueError("Amazon 承运商代码不能为空")
        if carrier_code.lower() in {"other", "others"} and not carrier_name:
            raise ValueError("其他承运商必须填写承运商名称")
        if not tracking_number:
            raise ValueError("Amazon 物流单号不能为空")
        if not package_reference_id.isdigit() or int(package_reference_id) <= 0:
            raise ValueError("Amazon 包裹序号必须是正整数字符串")
        try:
            ship_date = _time(input_data.get("ship_date"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Amazon 发货时间格式不正确") from exc
        return {
            "marketplace_id": marketplace_id,
            "carrier_code": carrier_code,
            "carrier_name": carrier_name,
            "tracking_number": tracking_number,
            "shipping_method": shipping_method,
            "package_reference_id": package_reference_id,
            "ship_date": ship_date,
        }

    async def _read_order(
        self,
        *,
        connection: PlatformConnection,
        order_id: str,
        included_data: list[str],
    ) -> tuple[str, dict]:
        refresh_token = self._refresh_token(connection)
        access_token = await AmazonSpApiService().refresh_access_token(
            refresh_token
        )
        order = await self.service.get_order(
            access_token=access_token,
            marketplace_id=str(connection.marketplace_id),
            order_id=order_id,
            included_data=included_data,
        )
        return access_token, order

    def _remaining_items(self, order: dict) -> list[dict]:
        items: list[dict] = []
        for item in order.get("orderItems") or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("orderItemId") or "").strip()
            ordered = max(0, int(item.get("quantityOrdered") or 0))
            fulfillment = item.get("fulfillment") or {}
            fulfilled = max(
                0,
                int(fulfillment.get("quantityFulfilled") or 0),
            )
            quantity = max(0, ordered - fulfilled)
            if item_id and quantity > 0:
                items.append(
                    {
                        "orderItemId": item_id,
                        "quantity": quantity,
                    }
                )
        return items

    def _validate_order(self, order: dict, marketplace_id: str) -> tuple[str, list[dict]]:
        """校验订单可发货并返回当前未发商品。"""

        order_marketplace_id = str(
            (order.get("salesChannel") or {}).get("marketplaceId") or ""
        ).strip()
        if order_marketplace_id != marketplace_id:
            raise ValueError("Amazon 订单不属于指定 Marketplace")
        fulfillment = order.get("fulfillment") or {}
        fulfilled_by = str(
            fulfillment.get("fulfilledBy") or ""
        ).upper()
        if fulfilled_by != "MERCHANT":
            raise ValueError("Amazon FBA 订单不能由卖家确认发货")
        status = str(
            fulfillment.get("fulfillmentStatus") or ""
        ).upper()
        if status in {"CANCELLED", "SHIPPED", "UNFULFILLABLE"}:
            raise ValueError("Amazon 订单当前状态不能确认发货")
        items = self._remaining_items(order)
        if not items:
            raise ValueError("Amazon 订单没有剩余可发货商品")
        return status, items

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "amazon.orders.fulfill":
            raise ValueError("适配器不支持该动作")
        order_id = str(target_id or "").strip()
        if not AMAZON_ORDER_ID_PATTERN.fullmatch(order_id):
            raise ValueError("Amazon 订单号格式不正确")
        values = self._input_values(input_data)
        connection = await self._connection(values["marketplace_id"])
        _access_token, order = await self._read_order(
            connection=connection,
            order_id=order_id,
            included_data=["FULFILLMENT"],
        )
        status, items = self._validate_order(
            order,
            values["marketplace_id"],
        )
        return {
            "order_id": order_id,
            "marketplace_id": values["marketplace_id"],
            "order_status": status,
            "carrier_code": values["carrier_code"],
            "carrier_name": values["carrier_name"],
            "tracking_number": values["tracking_number"],
            "ship_date": values["ship_date"].isoformat(),
            "package_reference_id": values["package_reference_id"],
            "item_count": sum(item["quantity"] for item in items),
            "item_count_distinct": len(items),
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        if action_id != "amazon.orders.fulfill":
            raise ValueError("适配器不支持该动作")
        values = self._input_values(input_data)
        connection = await self._connection(values["marketplace_id"])
        access_token, order = await self._read_order(
            connection=connection,
            order_id=target_id,
            included_data=["FULFILLMENT"],
        )
        _status, items = self._validate_order(
            order,
            values["marketplace_id"],
        )
        package_detail = {
            "packageReferenceId": values["package_reference_id"],
            "carrierCode": values["carrier_code"],
            "trackingNumber": values["tracking_number"],
            "shipDate": values["ship_date"].isoformat(),
            "orderItems": items,
        }
        if values["carrier_name"]:
            package_detail["carrierName"] = values["carrier_name"]
        if values["shipping_method"]:
            package_detail["shippingMethod"] = values["shipping_method"]
        await self.service.confirm_shipment(
            access_token=access_token,
            marketplace_id=values["marketplace_id"],
            order_id=target_id,
            package_detail=package_detail,
        )
        return ActionExecution(
            external_id=target_id,
            output={
                "order_id": target_id,
                "marketplace_id": values["marketplace_id"],
                "tracking_number": values["tracking_number"],
                "package_reference_id": values["package_reference_id"],
                "carrier_code": values["carrier_code"],
                "item_count": sum(item["quantity"] for item in items),
                "idempotency_key": idempotency_key,
            },
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        output = execution.output or {}
        marketplace_id = str(output.get("marketplace_id") or "").strip()
        if not marketplace_id:
            return ActionVerification(
                matched=False,
                details={"error": "Amazon 发货回读缺少 Marketplace"},
            )
        try:
            connection = await self._connection(marketplace_id)
            _access_token, order = await self._read_order(
                connection=connection,
                order_id=target_id,
                included_data=["FULFILLMENT", "PACKAGES"],
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        fulfillment = order.get("fulfillment") or {}
        status = str(
            fulfillment.get("fulfillmentStatus") or ""
        ).upper()
        tracking_number = str(
            output.get("tracking_number") or ""
        ).strip()
        package = next(
            (
                item
                for item in order.get("packages") or []
                if isinstance(item, dict)
                and str(item.get("trackingNumber") or "") == tracking_number
            ),
            None,
        )
        # 订单状态可能因其他包裹提前变化，只有当前物流单号可见才算本动作成功。
        matched = package is not None
        if not matched:
            return ActionVerification(
                matched=False,
                details={
                    "error": "Amazon 尚未返回对应物流单号",
                    "order_status": status,
                },
            )
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "order_id": str(order.get("orderId") or target_id),
                "marketplace_id": marketplace_id,
                "fulfillment_status": status,
                "tracking_number": tracking_number,
                "package_reference_id": (
                    str(package.get("packageReferenceId") or "")
                    if package is not None
                    else str(output.get("package_reference_id") or "")
                ),
                "package_status": (
                    (package.get("packageStatus") or {}).get("status")
                    if package is not None
                    else None
                ),
            },
            details={
                "verification_level": "external_readback",
                "tracking_matched": package is not None,
            },
        )
