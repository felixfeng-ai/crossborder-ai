"""Shopify 订单履约动作适配器。"""

from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.shopify_channel import ShopifyChannel
from app.services.action_runtime import ActionExecution, ActionVerification


def _normalize_order_id(value: str) -> str:
    normalized = str(value or "").strip().rsplit("/", 1)[-1]
    if not normalized.isdigit():
        raise ValueError("Shopify 订单编号格式不正确")
    return normalized


class ShopifyFulfillmentActionAdapter:
    """读取履约单、创建履约并回读承运商与物流单号。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.transport = transport

    async def _channel(self, input_data: dict) -> ShopifyChannel:
        try:
            channel_id = UUID(str(input_data["channel_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("缺少有效的 Shopify 店铺") from exc
        channel = await self.db.get(ShopifyChannel, channel_id)
        if (
            channel is None
            or channel.user_id != self.user_id
            or not channel.is_active
        ):
            raise ValueError("Shopify 店铺未连接或授权已失效")
        return channel

    @staticmethod
    def _channel_domain(channel: ShopifyChannel) -> str:
        domain = (channel.shop_domain or "").strip()
        if domain:
            return domain
        name = (channel.shop_name or "").replace(".myshopify.com", "").strip()
        return f"{name}.myshopify.com"

    def _api_url(self, channel: ShopifyChannel, path: str) -> str:
        return (
            f"https://{self._channel_domain(channel)}"
            f"/admin/api/{settings.SHOPIFY_API_VERSION}{path}"
        )

    def _headers(self, channel: ShopifyChannel) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": decrypt_value(channel.access_token),
            "Content-Type": "application/json",
        }

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport,
            timeout=20,
        )

    async def _read_fulfillment_orders(
        self,
        channel: ShopifyChannel,
        order_id: str,
    ) -> list[dict]:
        async with await self._client() as client:
            response = await client.get(
                self._api_url(
                    channel,
                    f"/orders/{order_id}/fulfillment_orders.json",
                ),
                headers=self._headers(channel),
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"读取 Shopify 履约单失败：{response.text[:200]}"
            )
        return response.json().get("fulfillment_orders") or []

    async def _read_fulfillments(
        self,
        channel: ShopifyChannel,
        order_id: str,
    ) -> list[dict]:
        async with await self._client() as client:
            response = await client.get(
                self._api_url(
                    channel,
                    f"/orders/{order_id}/fulfillments.json",
                ),
                headers=self._headers(channel),
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"读取 Shopify 履约结果失败：{response.text[:200]}"
            )
        return response.json().get("fulfillments") or []

    @staticmethod
    def _open_fulfillment_orders(
        fulfillment_orders: list[dict],
    ) -> list[dict]:
        result: list[dict] = []
        for item in fulfillment_orders:
            if item.get("status") not in {"open", "in_progress"}:
                continue
            line_items = [
                line
                for line in item.get("line_items") or []
                if int(line.get("remaining_quantity") or 0) > 0
            ]
            if line_items:
                result.append({**item, "line_items": line_items})
        return result

    @staticmethod
    def _duplicate(
        fulfillments: list[dict],
        tracking_number: str,
    ) -> dict | None:
        normalized = tracking_number.strip().lower()
        for fulfillment in fulfillments:
            number = str(
                fulfillment.get("tracking_number")
                or fulfillment.get("tracking_numbers", [""])[0]
            ).strip().lower()
            if number and number == normalized:
                return fulfillment
        return None

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        """确认履约单仍开放、物流信息完整且没有重复物流单号。"""

        if action_id != "orders.fulfill":
            raise ValueError("适配器不支持该动作")
        tracking_number = str(input_data.get("tracking_number") or "").strip()
        tracking_company = str(input_data.get("tracking_company") or "").strip()
        if not tracking_number:
            raise ValueError("请填写物流单号")
        if not tracking_company:
            raise ValueError("请填写承运商")

        order_id = _normalize_order_id(target_id)
        channel = await self._channel(input_data)
        fulfillment_orders = self._open_fulfillment_orders(
            await self._read_fulfillment_orders(channel, order_id)
        )
        if not fulfillment_orders:
            raise ValueError("该订单没有可履约的剩余商品")
        fulfillments = await self._read_fulfillments(channel, order_id)
        duplicate = self._duplicate(fulfillments, tracking_number)
        return {
            "order_id": order_id,
            "channel_id": str(channel.id),
            "fulfillment_order_ids": [
                int(item["id"]) for item in fulfillment_orders
            ],
            "line_item_count": sum(
                len(item["line_items"]) for item in fulfillment_orders
            ),
            "tracking_number": tracking_number,
            "tracking_company": tracking_company,
            "duplicate_fulfillment_id": (
                int(duplicate["id"]) if duplicate else None
            ),
            "fulfillment_orders": fulfillment_orders,
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        """创建履约；相同物流单号已存在时直接回放已有结果。"""

        snapshot = await self.preflight(
            action_id=action_id,
            target_id=target_id,
            input_data=input_data,
        )
        if snapshot["duplicate_fulfillment_id"] is not None:
            return ActionExecution(
                external_id=str(snapshot["duplicate_fulfillment_id"]),
                output={
                    "order_id": snapshot["order_id"],
                    "channel_id": snapshot["channel_id"],
                    "input_data": input_data,
                    "replayed": True,
                },
            )

        channel = await self._channel(input_data)
        order_id = snapshot["order_id"]
        requested_items = input_data.get("line_items_by_fulfillment_order")
        if requested_items:
            by_order = {
                int(item["fulfillment_order_id"]): item
                for item in requested_items
            }
            line_items_by_order = []
            for fulfillment_order in snapshot["fulfillment_orders"]:
                requested = by_order.get(int(fulfillment_order["id"]))
                if requested is None:
                    continue
                line_items_by_order.append(requested)
        else:
            line_items_by_order = [
                {
                    "fulfillment_order_id": int(item["id"]),
                    "fulfillment_order_line_items": [
                        {
                            "id": int(line["id"]),
                            "quantity": int(
                                line.get("remaining_quantity")
                                or line.get("quantity")
                                or 0
                            ),
                        }
                        for line in item["line_items"]
                    ],
                }
                for item in snapshot["fulfillment_orders"]
            ]
        if not line_items_by_order:
            raise ValueError("没有可提交的履约商品")

        payload = {
            "fulfillment": {
                "line_items_by_fulfillment_order": line_items_by_order,
                "tracking_info": {
                    "number": snapshot["tracking_number"],
                    "company": snapshot["tracking_company"],
                },
                "notify_customer": bool(
                    input_data.get("notify_customer", True)
                ),
            }
        }
        tracking_url = str(input_data.get("tracking_url") or "").strip()
        if tracking_url:
            payload["fulfillment"]["tracking_info"]["url"] = tracking_url

        async with await self._client() as client:
            response = await client.post(
                self._api_url(channel, "/fulfillments.json"),
                headers=self._headers(channel),
                json=payload,
            )
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"Shopify 创建履约失败：{response.text[:200]}"
            )
        fulfillment = response.json().get("fulfillment") or {}
        external_id = fulfillment.get("id")
        if external_id is None:
            raise RuntimeError("Shopify 未返回履约编号")
        return ActionExecution(
            external_id=str(external_id),
            output={
                "order_id": order_id,
                "channel_id": str(channel.id),
                "input_data": input_data,
                "replayed": False,
                "tracking_number": snapshot["tracking_number"],
                "tracking_company": snapshot["tracking_company"],
            },
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        """回读履约记录，确认状态和物流信息已经真实落库。"""

        if action_id != "orders.fulfill" or not execution.external_id:
            return ActionVerification(
                matched=False,
                details={"error": "缺少履约编号"},
            )
        output = execution.output or {}
        input_data = output.get("input_data") or {}
        channel = await self._channel(input_data)
        order_id = _normalize_order_id(target_id)
        fulfillments = await self._read_fulfillments(channel, order_id)
        target = next(
            (
                item
                for item in fulfillments
                if str(item.get("id")) == execution.external_id
            ),
            None,
        )
        if target is None:
            return ActionVerification(
                matched=False,
                snapshot={"order_id": order_id},
                details={"error": "回读未找到履约记录"},
            )

        expected_number = str(
            output.get("tracking_number")
            or input_data.get("tracking_number")
            or ""
        ).strip()
        expected_company = str(
            output.get("tracking_company")
            or input_data.get("tracking_company")
            or ""
        ).strip()
        actual_number = str(target.get("tracking_number") or "").strip()
        actual_company = str(target.get("tracking_company") or "").strip()
        mismatches: list[str] = []
        if target.get("status") != "success":
            mismatches.append("status")
        if actual_number != expected_number:
            mismatches.append("tracking_number")
        if actual_company != expected_company:
            mismatches.append("tracking_company")
        return ActionVerification(
            matched=not mismatches,
            snapshot={
                "order_id": order_id,
                "fulfillment_id": target.get("id"),
                "status": target.get("status"),
                "tracking_number": actual_number,
                "tracking_company": actual_company,
            },
            details={
                "expected_tracking_number": expected_number,
                "expected_tracking_company": expected_company,
                "mismatches": mismatches,
            },
        )
