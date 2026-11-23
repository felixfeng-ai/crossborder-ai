"""Temu LOCAL/SEMI 库存覆写受控动作适配器。"""

import hashlib
import json
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_signal import AgentSignal
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product_variant import ProductVariant
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.temu_inventory import TemuInventoryService


def _signal_payload(signal: AgentSignal) -> dict:
    try:
        value = json.loads(signal.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


class TemuInventoryUpdateActionAdapter:
    """精确映射 Temu SKU 后覆写普通库存，并强制回读。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        service: TemuInventoryService | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.service = service or TemuInventoryService(
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
            raise ValueError("Temu 库存动作编号格式不正确") from exc
        try:
            stock_target = int(input_data.get("stock_target"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu 目标库存必须是整数") from exc
        if stock_target < 0 or stock_target > 1_000_000:
            raise ValueError("Temu 库存必须在 0 至 1000000 之间")
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
        stock = await self.service.get_stock(
            connection_id=connection_id,
            goods_id=goods_id,
            out_sku_sns=[variant.sku],
        )
        if stock is None:
            raise ValueError("Temu 未返回该商品库存")
        matches = [
            item
            for item in stock.get("skus") or []
            if str(item.get("out_sku_sn") or "") == variant.sku
        ]
        if not matches:
            raise ValueError("Temu 库存中找不到对应外部 SKU")
        if len(matches) > 1:
            raise ValueError("Temu 外部 SKU 映射不唯一，拒绝猜测库存")
        remote_sku = matches[0]
        return {
            "listing": listing,
            "variant": variant,
            "connection": connection,
            "goods_id": goods_id,
            "sku_id": int(remote_sku["sku_id"]),
            "current_stock": int(remote_sku.get("stock") or 0),
            "stock_target": stock_target,
        }

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "temu.inventory.update":
            raise ValueError("适配器不支持该动作")
        context = await self._context(target_id, input_data)
        return {
            "listing_id": str(context["listing"].id),
            "variant_id": str(context["variant"].id),
            "sku": context["variant"].sku,
            "connection_id": str(context["connection"].id),
            "goods_id": context["goods_id"],
            "sku_id": context["sku_id"],
            "current_stock": context["current_stock"],
            "stock_target": context["stock_target"],
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
        request_key = "temu-stock:" + hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()
        result = await self.service.update_stock(
            connection_id=context["connection"].id,
            goods_id=context["goods_id"],
            sku_id=context["sku_id"],
            stock_target=context["stock_target"],
            request_unique_key=request_key,
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
                "stock_target": context["stock_target"],
                "request_unique_key": request_key,
                "result": result,
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
            sku_id = int(output["sku_id"])
            stock_target = int(output["stock_target"])
            sku = str(output["sku"])
            stock = await self.service.get_stock(
                connection_id=connection_id,
                goods_id=goods_id,
                out_sku_sns=[sku],
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        if stock is None:
            return ActionVerification(
                matched=False,
                details={"error": "Temu 库存回读为空"},
            )
        remote = next(
            (
                item
                for item in stock.get("skus") or []
                if int(item.get("sku_id") or 0) == sku_id
            ),
            None,
        )
        if remote is None or int(remote.get("stock") or 0) != stock_target:
            return ActionVerification(
                matched=False,
                details={"error": "Temu 库存回读与目标值不一致"},
            )
        try:
            variant = await self.db.get(
                ProductVariant,
                UUID(str(output["variant_id"])),
            )
            if variant is not None:
                variant.stock_quantity = stock_target
                await self.db.flush()
        except (TypeError, ValueError):
            pass
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "goods_id": goods_id,
                "sku_id": sku_id,
                "sku": sku,
                "stock": stock_target,
            },
            details={
                "verification_level": "platform_readback",
                "stock_matched": True,
            },
        )
