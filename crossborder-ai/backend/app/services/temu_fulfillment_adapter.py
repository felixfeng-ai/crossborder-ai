"""Temu LOCAL/SEMI 自发货受控动作适配器。"""

import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.temu_fulfillment import TemuFulfillmentService


TRACKING_NUMBER_PATTERN = re.compile(r"[^A-Za-z0-9]")


class TemuOrderFulfillmentActionAdapter:
    """预检、提交并回读 Temu 卖家自履约发货结果。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        service: TemuFulfillmentService | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.service = service or TemuFulfillmentService(
            db,
            user_id=user_id,
        )

    def _input_values(self, input_data: dict) -> dict:
        try:
            connection_id = UUID(
                str(input_data.get("connection_id") or "")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu 店铺连接 ID 格式不正确") from exc
        parent_order_sn = str(
            input_data.get("parent_order_sn") or ""
        ).strip()
        if not parent_order_sn:
            raise ValueError("Temu 父订单号不能为空")
        try:
            carrier_id = int(input_data.get("carrier_id") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu 承运商编号不正确") from exc
        if carrier_id <= 0:
            raise ValueError("Temu 承运商编号不正确")
        tracking_number = TRACKING_NUMBER_PATTERN.sub(
            "",
            str(input_data.get("tracking_number") or "").strip(),
        ).upper()
        if not tracking_number:
            raise ValueError("Temu 物流单号不能为空")
        warehouse_id = str(
            input_data.get("self_shipping_warehouse_id") or ""
        ).strip()
        return {
            "connection_id": connection_id,
            "parent_order_sn": parent_order_sn,
            "carrier_id": carrier_id,
            "tracking_number": tracking_number,
            "self_shipping_warehouse_id": warehouse_id,
        }

    async def _shipments_match(
        self,
        *,
        connection_id: UUID,
        parent_order_sn: str,
        order_sns: list[str],
        tracking_number: str,
    ) -> bool:
        if not order_sns:
            return False
        for order_sn in order_sns:
            shipment = await self.service.get_shipment(
                connection_id=connection_id,
                parent_order_sn=parent_order_sn,
                order_sn=order_sn,
            )
            if tracking_number not in shipment["tracking_numbers"]:
                return False
        return True

    def _order_lines(self, detail: dict) -> list[dict]:
        lines = detail["active_lines"]
        if not lines:
            raise ValueError("Temu 订单没有可发货商品")
        if any(
            item["fulfillment_type"] != "fulfillBySeller"
            for item in lines
        ):
            raise ValueError("Temu 合作仓订单不能由卖家自发货")
        return lines

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "temu.orders.fulfill":
            raise ValueError("适配器不支持该动作")
        values = self._input_values(input_data)
        if values["parent_order_sn"] != str(target_id or "").strip():
            raise ValueError("Temu 动作目标与父订单号不一致")
        detail = await self.service.get_order_detail(
            connection_id=values["connection_id"],
            parent_order_sn=values["parent_order_sn"],
        )
        lines = self._order_lines(detail)
        order_sns = [item["order_sn"] for item in lines]
        if not all(order_sns):
            raise ValueError("Temu 订单行缺少子订单号")
        shipping_times = [
            item["shipping_time"] for item in detail["lines"]
        ]
        if any(value > 0 for value in shipping_times) and not detail["shipped"]:
            raise ValueError("Temu 订单已部分发货，不能重复确认")
        already_shipped = False
        if detail["shipped"]:
            matched = await self._shipments_match(
                connection_id=values["connection_id"],
                parent_order_sn=values["parent_order_sn"],
                order_sns=order_sns,
                tracking_number=values["tracking_number"],
            )
            if not matched:
                raise ValueError("Temu 订单已发货，但物流单号不一致")
            already_shipped = True
        carriers = await self.service.list_carriers(
            connection_id=values["connection_id"],
            region_id=detail["region_id"],
        )
        carrier = next(
            (
                item
                for item in carriers
                if item["carrier_id"] == values["carrier_id"]
            ),
            None,
        )
        if carrier is None:
            raise ValueError("Temu 当前区域不支持所选承运商")
        return {
            "connection_id": str(values["connection_id"]),
            "parent_order_sn": values["parent_order_sn"],
            "region_id": detail["region_id"],
            "carrier_id": carrier["carrier_id"],
            "carrier_name": carrier["name"],
            "tracking_number": values["tracking_number"],
            "self_shipping_warehouse_id": values[
                "self_shipping_warehouse_id"
            ],
            "item_count": detail["item_count"],
            "order_sns": order_sns,
            "order_lines": [
                {
                    "order_sn": item["order_sn"],
                    "goods_id": item["goods_id"],
                    "sku_id": item["sku_id"],
                    "quantity": item["quantity"],
                }
                for item in lines
            ],
            "already_shipped": already_shipped,
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        snapshot = await self.preflight(
            action_id=action_id,
            target_id=target_id,
            input_data=input_data,
        )
        confirmation_warnings: list[str] = []
        if not snapshot["already_shipped"]:
            package = {
                "carrierId": snapshot["carrier_id"],
                "trackingNumber": snapshot["tracking_number"],
                "orderSendInfoList": [
                    {
                        "parentOrderSn": snapshot["parent_order_sn"],
                        "orderSn": item["order_sn"],
                        "goodsId": item["goods_id"],
                        "skuId": item["sku_id"],
                        "quantity": item["quantity"],
                    }
                    for item in snapshot["order_lines"]
                ],
            }
            if snapshot["self_shipping_warehouse_id"]:
                package["selfShippingWarehouseId"] = snapshot[
                    "self_shipping_warehouse_id"
                ]
            confirmation = await self.service.confirm_shipment(
                connection_id=UUID(snapshot["connection_id"]),
                payload={
                    "sendType": 0,
                    "sendRequestList": [package],
                },
            )
            confirmation_warnings = list(
                confirmation.get("warnings") or []
            )
        return ActionExecution(
            external_id=snapshot["parent_order_sn"],
            output=snapshot
            | {
                "idempotency_key": idempotency_key,
                "warnings": confirmation_warnings,
            },
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        if action_id != "temu.orders.fulfill":
            raise ValueError("适配器不支持该动作")
        output = execution.output or {}
        connection_id = str(output.get("connection_id") or "").strip()
        parent_order_sn = str(
            output.get("parent_order_sn") or target_id
        ).strip()
        tracking_number = str(
            output.get("tracking_number") or ""
        ).strip()
        order_sns = [
            str(item)
            for item in output.get("order_sns") or []
            if str(item).strip()
        ]
        try:
            matched = await self._shipments_match(
                connection_id=UUID(connection_id),
                parent_order_sn=parent_order_sn,
                order_sns=order_sns,
                tracking_number=tracking_number,
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        if not matched:
            return ActionVerification(
                matched=False,
                details={"error": "Temu 尚未回读全部子订单的物流单号"},
            )
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "parent_order_sn": parent_order_sn,
                "tracking_number": tracking_number,
                "order_sn_count": len(order_sns),
            },
            details={
                "verification_level": "external_readback",
                "all_order_lines_matched": True,
            },
        )
