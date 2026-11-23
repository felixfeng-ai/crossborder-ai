"""Shopify 单笔退款动作适配器。"""

import json
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.action_run import ActionRun
from app.models.shopify_channel import ShopifyChannel
from app.services.action_runtime import ActionExecution, ActionVerification


class ShopifyRefundActionAdapter:
    """按单笔订单退款，所有金额都以 Shopify 回读结果为准。"""

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
    def _domain(channel: ShopifyChannel) -> str:
        domain = (channel.shop_domain or "").strip()
        if domain:
            return domain
        name = (channel.shop_name or "").replace(".myshopify.com", "").strip()
        return f"{name}.myshopify.com"

    def _url(self, channel: ShopifyChannel, path: str) -> str:
        return (
            f"https://{self._domain(channel)}"
            f"/admin/api/{settings.SHOPIFY_API_VERSION}{path}"
        )

    def _headers(self, channel: ShopifyChannel) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": decrypt_value(channel.access_token),
            "Content-Type": "application/json",
        }

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=20)

    async def _read_order(self, channel: ShopifyChannel, order_id: str) -> dict:
        async with await self._client() as client:
            response = await client.get(
                self._url(channel, f"/orders/{order_id}.json"),
                headers=self._headers(channel),
            )
        if response.status_code != 200:
            raise RuntimeError(f"读取 Shopify 订单失败：{response.text[:200]}")
        return response.json().get("order") or {}

    async def _read_refunds(
        self,
        channel: ShopifyChannel,
        order_id: str,
    ) -> list[dict]:
        async with await self._client() as client:
            response = await client.get(
                self._url(channel, f"/orders/{order_id}/refunds.json"),
                headers=self._headers(channel),
            )
        if response.status_code != 200:
            raise RuntimeError(f"读取 Shopify 退款记录失败：{response.text[:200]}")
        return response.json().get("refunds") or []

    @staticmethod
    def _amount(value) -> Decimal:
        try:
            return Decimal(str(value or "0")).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("退款金额格式不正确") from exc

    @classmethod
    def _refunded_amount(cls, refunds: list[dict]) -> Decimal:
        total = Decimal("0.00")
        for refund in refunds:
            for transaction in refund.get("transactions") or []:
                if transaction.get("kind") != "refund":
                    continue
                if transaction.get("status") not in (None, "success"):
                    continue
                total += cls._amount(transaction.get("amount"))
        return total

    async def _daily_refunded(self) -> Decimal:
        """从持久化动作记录汇总当天成功退款，跨进程重启不会清零。"""

        now = datetime.now(timezone.utc)
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        runs = (
            await self.db.execute(
                select(ActionRun).where(
                    ActionRun.action_id == "refunds.create",
                    ActionRun.status == "succeeded",
                    ActionRun.confirmed_by_user_id == self.user_id,
                    ActionRun.finished_at >= start,
                    ActionRun.after_snapshot_json.is_not(None),
                )
            )
        ).scalars().all()
        total = Decimal("0.00")
        for run in runs:
            try:
                snapshot = json.loads(run.after_snapshot_json or "{}")
            except json.JSONDecodeError:
                continue
            if isinstance(snapshot, dict):
                try:
                    total += self._amount(snapshot.get("amount"))
                except ValueError:
                    continue
        return total

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        """在真实执行前核对订单余额、单次上限和持久化日限额。"""

        if action_id != "refunds.create":
            raise ValueError("适配器不支持该动作")
        order_id = str(target_id or "").strip().rsplit("/", 1)[-1]
        if not order_id.isdigit():
            raise ValueError("Shopify 订单编号格式不正确")
        amount = self._amount(input_data.get("amount"))
        if amount <= 0:
            raise ValueError("退款金额必须大于 0")
        if amount > self._amount(settings.MAX_REFUND_AMOUNT):
            raise ValueError("退款金额超过单次上限")

        channel = await self._channel(input_data)
        order = await self._read_order(channel, order_id)
        total = self._amount(order.get("total_price"))
        refunds = await self._read_refunds(channel, order_id)
        refunded = self._refunded_amount(refunds)
        refundable = max(Decimal("0.00"), total - refunded)
        if amount > refundable:
            raise ValueError(f"退款金额不能超过可退金额 {refundable:.2f}")

        used = await self._daily_refunded()
        if used + amount > self._amount(settings.MAX_DAILY_REFUND_TOTAL):
            raise ValueError("今日累计退款已达单日上限")
        return {
            "order_id": order_id,
            "channel_id": str(channel.id),
            "currency": order.get("currency") or "USD",
            "total_amount": float(total),
            "refunded_amount": float(refunded),
            "refundable_amount": float(refundable),
            "amount": float(amount),
            "reason": str(input_data.get("reason") or "").strip(),
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        """发起退款，重复幂等键只回放已有退款记录。"""

        snapshot = await self.preflight(
            action_id=action_id,
            target_id=target_id,
            input_data=input_data,
        )
        channel = await self._channel(input_data)
        order_id = snapshot["order_id"]
        refunds = await self._read_refunds(channel, order_id)
        marker = f"VeyaShip action {idempotency_key}"
        existing = next(
            (
                refund
                for refund in refunds
                if marker in str(refund.get("note") or "")
            ),
            None,
        )
        if existing is not None:
            return ActionExecution(
                external_id=str(existing.get("id")),
                output={
                    "order_id": order_id,
                    "channel_id": str(channel.id),
                    "input_data": input_data,
                    "amount": snapshot["amount"],
                    "replayed": True,
                },
            )

        order = await self._read_order(channel, order_id)
        amount = self._amount(snapshot["amount"])
        reason = snapshot["reason"] or "VeyaShip 退款"
        note = f"{reason} · {marker}"
        gateway = (
            (order.get("payment_gateway_names") or [order.get("gateway") or ""])[0]
        )
        payload = {
            "refund": {
                "notify": bool(input_data.get("notify_customer", True)),
                "note": note,
                "transactions": [
                    {
                        "kind": "refund",
                        "amount": f"{amount:.2f}",
                        "gateway": gateway,
                    }
                ],
                "refund_line_items": [],
            }
        }
        async with await self._client() as client:
            response = await client.post(
                self._url(channel, f"/orders/{order_id}/refunds.json"),
                headers=self._headers(channel),
                json=payload,
            )
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"Shopify 退款失败：{response.text[:200]}")
        refund = response.json().get("refund") or {}
        refund_id = refund.get("id")
        if refund_id is None:
            raise RuntimeError("Shopify 未返回退款编号")
        return ActionExecution(
            external_id=str(refund_id),
            output={
                "order_id": order_id,
                "channel_id": str(channel.id),
                "input_data": input_data,
                "amount": float(amount),
                "note": note,
                "replayed": False,
            },
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        """按退款编号回读金额和交易，接口成功不等于退款完成。"""

        if action_id != "refunds.create" or not execution.external_id:
            return ActionVerification(
                matched=False,
                details={"error": "缺少退款编号"},
            )
        output = execution.output or {}
        channel = await self._channel(output.get("input_data") or {})
        order_id = str(target_id or "").strip().rsplit("/", 1)[-1]
        refunds = await self._read_refunds(channel, order_id)
        refund = next(
            (
                item
                for item in refunds
                if str(item.get("id")) == execution.external_id
            ),
            None,
        )
        if refund is None:
            return ActionVerification(
                matched=False,
                snapshot={"order_id": order_id},
                details={"error": "回读未找到退款记录"},
            )
        amount = self._refunded_amount([refund])
        expected = self._amount(output.get("amount"))
        return ActionVerification(
            matched=amount == expected,
            snapshot={
                "order_id": order_id,
                "refund_id": refund.get("id"),
                "amount": float(amount),
                "status": "refunded",
            },
            details={
                "expected_amount": float(expected),
                "actual_amount": float(amount),
                "mismatches": [] if amount == expected else ["amount"],
            },
        )
