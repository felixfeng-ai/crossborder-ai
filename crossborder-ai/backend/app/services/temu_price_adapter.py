"""Temu LOCAL/SEMI 供货价变更受控动作适配器。"""

import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_signal import AgentSignal
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product_variant import ProductVariant
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.temu_price import TemuPriceService


def _signal_payload(signal: AgentSignal) -> dict:
    try:
        value = json.loads(signal.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _price_string(value) -> str:
    try:
        return format(Decimal(str(value)), "f")
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Temu 供货价格式不正确") from exc


class TemuPriceUpdateActionAdapter:
    """预检价格审核状态、提交供货价并回读价格审核单。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        service: TemuPriceService | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.service = service or TemuPriceService(
            db,
            user_id=user_id,
        )

    async def _goods_id(
        self,
        *,
        listing_id: UUID,
        connection_id: UUID,
    ) -> int:
        signals = (
            await self.db.execute(
                select(AgentSignal)
                .where(
                    AgentSignal.workspace_id == self.workspace_id,
                    AgentSignal.signal_type
                    == "temu_listing_processing",
                )
                .order_by(
                    desc(AgentSignal.observed_at),
                    desc(AgentSignal.version),
                )
                .limit(100)
            )
        ).scalars().all()
        for signal in signals:
            payload = _signal_payload(signal)
            if (
                str(payload.get("listing_id") or "")
                == str(listing_id)
                and str(payload.get("connection_id") or "")
                == str(connection_id)
            ):
                goods_id = int(payload.get("goods_id") or 0)
                if goods_id > 0:
                    return goods_id
        raise ValueError("Temu Listing 尚未记录可用的 goodsId")

    async def _context(self, target_id: str, input_data: dict) -> dict:
        try:
            listing_id = UUID(
                str(input_data.get("listing_id") or target_id)
            )
            connection_id = UUID(
                str(input_data.get("connection_id") or "")
            )
            variant_id = UUID(str(input_data.get("variant_id") or ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu 价格动作编号格式不正确") from exc
        amount = _price_string(input_data.get("amount"))
        if Decimal(amount) <= 0:
            raise ValueError("Temu 新供货价必须大于 0")
        currency = str(input_data.get("currency") or "").strip().upper()
        if not currency:
            raise ValueError("Temu 新供货价币种不能为空")
        reason = str(input_data.get("reason") or "").strip()
        if not reason:
            raise ValueError("Temu 价格变更原因不能为空")
        listing = (
            await self.db.execute(
                select(ListingDraft).where(
                    ListingDraft.id == listing_id,
                    ListingDraft.workspace_id == self.workspace_id,
                    ListingDraft.platform == "temu",
                )
            )
        ).scalar_one_or_none()
        if listing is None:
            raise ValueError("Temu Listing 不存在或不属于当前工作区")
        variant = (
            await self.db.execute(
                select(ProductVariant).where(
                    ProductVariant.id == variant_id,
                    ProductVariant.product_id == listing.product_id,
                    ProductVariant.workspace_id == self.workspace_id,
                    ProductVariant.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if variant is None:
            raise ValueError("Temu SKU 不存在或不属于当前商品")
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
            raise ValueError("Temu 店铺连接不存在或授权不可用")
        goods_id = await self._goods_id(
            listing_id=listing_id,
            connection_id=connection_id,
        )
        remote_sku = await self.service.get_product_sku(
            connection_id=connection_id,
            goods_id=goods_id,
            out_sku_sn=variant.sku,
        )
        if remote_sku is None:
            raise ValueError("Temu 商品中找不到可变更价格的 SKU")
        workflow = await self.service.get_price_workflow(
            connection_id=connection_id,
            goods_id=goods_id,
        )
        if not workflow.get("allows_change"):
            raise ValueError("Temu 价格正在审核或等待卖家确认，暂不能改价")
        return {
            "listing": listing,
            "variant": variant,
            "connection": connection,
            "goods_id": goods_id,
            "sku_id": int(remote_sku["sku_id"]),
            "amount": amount,
            "currency": currency,
            "reason": reason,
            "workflow": workflow,
        }

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "temu.pricing.submit":
            raise ValueError("适配器不支持该动作")
        context = await self._context(target_id, input_data)
        return {
            "listing_id": str(context["listing"].id),
            "variant_id": str(context["variant"].id),
            "sku": context["variant"].sku,
            "connection_id": str(context["connection"].id),
            "goods_id": context["goods_id"],
            "sku_id": context["sku_id"],
            "current_local_price": _price_string(
                context["variant"].price
            ),
            "amount": context["amount"],
            "currency": context["currency"],
            "reason": context["reason"],
            "current_price_order_ids": [
                item["order_id"]
                for item in context["workflow"]["price_audit_list"]
                if item.get("order_id")
            ],
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        context = await self._context(target_id, input_data)
        accepted = await self.service.submit_price_change(
            connection_id=context["connection"].id,
            goods_id=context["goods_id"],
            sku_id=context["sku_id"],
            amount=context["amount"],
            currency=context["currency"],
            reason=context["reason"],
        )
        return ActionExecution(
            external_id=f"{context['goods_id']}:{context['sku_id']}",
            output={
                "listing_id": str(context["listing"].id),
                "variant_id": str(context["variant"].id),
                "connection_id": str(context["connection"].id),
                "goods_id": context["goods_id"],
                "sku_id": context["sku_id"],
                "sku": context["variant"].sku,
                "amount": context["amount"],
                "currency": context["currency"],
                "reason": context["reason"],
                "previous_order_ids": [
                    item["order_id"]
                    for item in context["workflow"]["price_audit_list"]
                    if item.get("order_id")
                ],
                "accepted": accepted,
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
        try:
            connection_id = UUID(str(output["connection_id"]))
            goods_id = int(output["goods_id"])
            workflow = await self.service.get_price_workflow(
                connection_id=connection_id,
                goods_id=goods_id,
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        previous_ids = {
            str(item)
            for item in output.get("previous_order_ids") or []
            if str(item)
        }
        current_ids = {
            str(item["order_id"])
            for item in workflow.get("price_audit_list") or []
            if item.get("order_id")
        }
        new_order_ids = sorted(current_ids - previous_ids)
        if not new_order_ids:
            return ActionVerification(
                matched=False,
                details={"error": "Temu 尚未回读新的价格审核单"},
            )
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "goods_id": goods_id,
                "sku_id": int(output["sku_id"]),
                "amount": str(output["amount"]),
                "currency": str(output["currency"]),
                "state": "submitted_for_review",
                "new_order_ids": new_order_ids,
                "price_audit_list": workflow.get("price_audit_list") or [],
            },
            details={
                "verification_level": "price_workflow_readback",
                "state_not_shelf_price": True,
            },
        )
