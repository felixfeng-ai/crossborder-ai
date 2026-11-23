"""Shopify 订单取消动作适配器。"""

from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.shopify_channel import ShopifyChannel
from app.services.action_runtime import ActionExecution, ActionVerification


class ShopifyOrderCancelActionAdapter:
    """取消未履约订单，支持退款、回补库存和幂等回读。"""

    ALLOWED_REASONS = {"customer", "fraud", "inventory", "declined", "other"}

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.transport = transport

    async def _channel(self, input_data: dict) -> ShopifyChannel:
        try:
            channel_id = UUID(str(input_data.get("channel_id") or ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("缺少有效的 Shopify 店铺") from exc
        channel = await self.db.get(ShopifyChannel, channel_id)
        if (
            channel is None
            or channel.user_id != self.user_id
            or channel.workspace_id != self.workspace_id
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

    async def _request(
        self,
        channel: ShopifyChannel,
        method: str,
        path: str,
        *,
        json_data: dict | None = None,
    ) -> dict:
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=20,
        ) as client:
            response = await client.request(
                method,
                self._api_url(channel, path),
                headers=self._headers(channel),
                json=json_data,
            )
        if response.status_code == 429:
            raise RuntimeError("Shopify 限流，请稍后重试")
        if response.status_code == 401:
            raise ValueError("Shopify 店铺授权已失效")
        if response.status_code >= 400:
            raise RuntimeError(
                f"Shopify 订单取消失败：{response.text[:200]}"
            )
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _order_id(value: str) -> str:
        normalized = str(value or "").strip().rsplit("/", 1)[-1]
        if not normalized.isdigit():
            raise ValueError("Shopify 订单编号格式不正确")
        return normalized

    async def _read_order(
        self,
        channel: ShopifyChannel,
        order_id: str,
    ) -> dict:
        payload = await self._request(
            channel,
            "GET",
            f"/orders/{order_id}.json",
        )
        order = payload.get("order") or {}
        if not order:
            raise ValueError("Shopify 订单不存在")
        return order

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "orders.cancel":
            raise ValueError("适配器不支持该动作")
        channel = await self._channel(input_data)
        order_id = self._order_id(target_id)
        order = await self._read_order(channel, order_id)
        already_cancelled = bool(order.get("cancelled_at"))
        fulfillment_status = str(order.get("fulfillment_status") or "")
        if not already_cancelled and fulfillment_status == "fulfilled":
            raise ValueError("订单已履约，不能直接取消，请走退货退款流程")
        reason = str(input_data.get("reason") or "customer").strip().lower()
        if reason not in self.ALLOWED_REASONS:
            raise ValueError("不支持的订单取消原因")
        notify_customer = bool(input_data.get("notify_customer", True))
        customer_email = str(order.get("email") or "")
        if notify_customer and not customer_email and not already_cancelled:
            raise ValueError("订单缺少买家邮箱，无法发送取消通知")
        return {
            "channel_id": str(channel.id),
            "order_id": order_id,
            "already_cancelled": already_cancelled,
            "reason": reason,
            "restock": bool(input_data.get("restock", True)),
            "refund": bool(input_data.get("refund", False)),
            "notify_customer": notify_customer,
            "customer_email": customer_email,
            "financial_status": order.get("financial_status"),
            "fulfillment_status": fulfillment_status or None,
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
        if snapshot["already_cancelled"]:
            return ActionExecution(
                external_id=snapshot["order_id"],
                output={
                    "order_id": snapshot["order_id"],
                    "channel_id": snapshot["channel_id"],
                    "input_data": input_data,
                    "replayed": True,
                    "idempotency_key": idempotency_key,
                },
            )
        channel = await self._channel(input_data)
        body = {
            "reason": snapshot["reason"],
            "restock": snapshot["restock"],
            "refund": snapshot["refund"],
        }
        if snapshot["notify_customer"] and snapshot["customer_email"]:
            body["email"] = snapshot["customer_email"]
        await self._request(
            channel,
            "POST",
            f"/orders/{snapshot['order_id']}/cancel.json",
            json_data=body,
        )
        return ActionExecution(
            external_id=snapshot["order_id"],
            output={
                "order_id": snapshot["order_id"],
                "channel_id": snapshot["channel_id"],
                "input_data": input_data,
                "restock": snapshot["restock"],
                "refund": snapshot["refund"],
                "notify_customer": snapshot["notify_customer"],
                "replayed": False,
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
        channel = await self._channel(
            {"channel_id": output.get("channel_id")}
        )
        order = await self._read_order(
            channel,
            self._order_id(target_id),
        )
        cancelled_at = order.get("cancelled_at")
        return ActionVerification(
            matched=bool(cancelled_at),
            terminal=True,
            snapshot={
                "order_id": str(order.get("id") or target_id),
                "cancelled_at": cancelled_at,
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
            },
            details={
                "mismatches": [] if cancelled_at else ["cancelled_at"],
            },
        )
