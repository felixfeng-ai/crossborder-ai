"""Amazon Listing 库存与售价局部分更新动作适配器。"""

import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product_variant import ProductVariant
from app.models.workspace import Workspace
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.amazon_listing_publish import AmazonListingPublishService


class AmazonOfferUpdateAdapter:
    """通过部分 PATCH 修改单个 Amazon Listing 的库存或售价。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        service: AmazonListingPublishService | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.service = service or AmazonListingPublishService()

    async def _context(self, target_id: str, input_data: dict):
        try:
            listing_id = UUID(str(input_data.get("listing_id") or target_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Amazon Listing 编号格式不正确") from exc
        listing = (
            await self.db.execute(
                select(ListingDraft).where(
                    ListingDraft.id == listing_id,
                    ListingDraft.workspace_id == self.workspace_id,
                    ListingDraft.platform == "amazon",
                )
            )
        ).scalar_one_or_none()
        if listing is None:
            raise ValueError("Amazon Listing 不存在或不属于当前工作区")
        if listing.compliance_status != "passed":
            raise ValueError("Amazon Listing 当前版本尚未通过合规检查")
        try:
            variant_id = UUID(str(input_data.get("variant_id") or ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("Amazon 变体编号格式不正确") from exc
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
            raise ValueError("Amazon Listing 缺少有效变体")
        marketplace_id = str(
            input_data.get("marketplace_id") or ""
        ).strip()
        if not marketplace_id:
            raise ValueError("Amazon Marketplace ID 不能为空")
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
        credentials = json.loads(decrypt_value(connection.credentials))
        refresh_token = str(
            credentials.get("refresh_token") or ""
        ).strip()
        if not refresh_token:
            raise ValueError("Amazon 店铺授权缺少 Refresh Token")
        return {
            "listing": listing,
            "variant": variant,
            "connection": connection,
            "refresh_token": refresh_token,
            "marketplace_id": marketplace_id,
        }

    async def _remote(self, context: dict) -> dict:
        remote = await self.service.get_listing(
            refresh_token=context["refresh_token"],
            seller_id=context["connection"].external_account_id,
            marketplace_id=context["marketplace_id"],
            sku=context["variant"].sku,
            included_data="summaries,attributes,issues",
        )
        if remote is None:
            raise ValueError("Amazon 尚未返回该 Listing")
        return remote

    def _product_type(self, remote: dict, input_data: dict) -> str:
        summaries = [
            item
            for item in remote.get("summaries") or []
            if isinstance(item, dict)
        ]
        product_type = str(
            (summaries[0].get("productType") if summaries else "")
            or input_data.get("product_type")
            or ""
        ).strip()
        if not product_type:
            raise ValueError("Amazon product type 不能为空")
        return product_type

    def _stock(self, remote: dict) -> int | None:
        attributes = remote.get("attributes") or {}
        items = attributes.get("fulfillment_availability") or []
        if not isinstance(items, list) or not items:
            return None
        try:
            return int(items[0].get("quantity"))
        except (TypeError, ValueError, AttributeError):
            return None

    def _price(self, remote: dict) -> tuple[Decimal | None, str]:
        attributes = remote.get("attributes") or {}
        offers = attributes.get("purchasable_offer") or []
        if not isinstance(offers, list) or not offers:
            return None, ""
        offer = offers[0]
        if not isinstance(offer, dict):
            return None, ""
        try:
            amount = offer["our_price"][0]["schedule"][0]["value_with_tax"]
            return Decimal(str(amount)), str(offer.get("currency") or "")
        except (KeyError, IndexError, TypeError, InvalidOperation):
            return None, ""

    def _update(self, action_id: str, context: dict, input_data: dict) -> dict:
        if action_id == "amazon.inventory.update":
            try:
                stock = int(input_data.get("stock_quantity"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Amazon 库存数量必须是整数") from exc
            if stock < 0:
                raise ValueError("Amazon 库存数量不能小于 0")
            return {
                "path": "/attributes/fulfillment_availability",
                "value": [
                    {
                        "fulfillment_channel_code": "DEFAULT",
                        "quantity": stock,
                    }
                ],
                "target": str(stock),
            }
        if action_id == "amazon.pricing.update":
            try:
                price = Decimal(str(input_data.get("price"))).quantize(
                    Decimal("0.01")
                )
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("Amazon 售价格式不正确") from exc
            if price <= 0:
                raise ValueError("Amazon 售价必须大于 0")
            currency = str(input_data.get("currency") or "").strip().upper()
            if not currency:
                raise ValueError("Amazon 售价币种不能为空")
            return {
                "path": "/attributes/purchasable_offer",
                "value": [
                    {
                        "marketplace_id": context["marketplace_id"],
                        "currency": currency,
                        "audience": "ALL",
                        "our_price": [
                            {
                                "schedule": [
                                    {
                                        "value_with_tax": float(price),
                                    }
                                ]
                            }
                        ],
                    }
                ],
                "target": f"{price:.2f} {currency}",
            }
        raise ValueError("适配器不支持该动作")

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        context = await self._context(target_id, input_data)
        remote = await self._remote(context)
        product_type = self._product_type(remote, input_data)
        update = self._update(action_id, context, input_data)
        before_value = (
            str(self._stock(remote))
            if action_id == "amazon.inventory.update"
            else (
                lambda value: f"{value[0]:.2f} {value[1]}"
                if value[0] is not None
                else "未知"
            )(self._price(remote))
        )
        preview = await self.service.patch_listing(
            refresh_token=context["refresh_token"],
            seller_id=context["connection"].external_account_id,
            marketplace_id=context["marketplace_id"],
            sku=context["variant"].sku,
            product_type=product_type,
            patches=[
                {
                    "op": "replace",
                    "path": update["path"],
                    "value": update["value"],
                }
            ],
            preview=True,
        )
        status = str(preview.get("status") or "VALIDATION_PREVIEW").upper()
        if status in {"INVALID", "ERROR"}:
            raise ValueError("Amazon Listing PATCH 预检未通过")
        return {
            "listing_id": str(context["listing"].id),
            "variant_id": str(context["variant"].id),
            "sku": context["variant"].sku,
            "marketplace_id": context["marketplace_id"],
            "product_type": product_type,
            "attribute_path": update["path"],
            "before_value": before_value,
            "after_value": update["target"],
            "preview_status": status,
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
        remote = await self._remote(context)
        product_type = self._product_type(remote, input_data)
        update = self._update(action_id, context, input_data)
        response = await self.service.patch_listing(
            refresh_token=context["refresh_token"],
            seller_id=context["connection"].external_account_id,
            marketplace_id=context["marketplace_id"],
            sku=context["variant"].sku,
            product_type=product_type,
            patches=[
                {
                    "op": "replace",
                    "path": update["path"],
                    "value": update["value"],
                }
            ],
            preview=False,
        )
        status = str(response.get("status") or "ACCEPTED").upper()
        if status in {"INVALID", "ERROR"}:
            raise RuntimeError("Amazon Listing PATCH 提交未通过")
        return ActionExecution(
            external_id=str(context["listing"].id),
            output={
                "listing_id": str(context["listing"].id),
                "variant_id": str(context["variant"].id),
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "product_type": product_type,
                "attribute_path": update["path"],
                "target_value": update["target"],
                "status": status,
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
            context = await self._context(
                target_id,
                {
                    "listing_id": output.get("listing_id") or target_id,
                    "variant_id": output.get("variant_id"),
                    "marketplace_id": output.get("marketplace_id"),
                    "product_type": output.get("product_type"),
                },
            )
            remote = await self._remote(context)
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        if action_id == "amazon.inventory.update":
            actual = self._stock(remote)
            target = int(output.get("target_value") or 0)
            matched = actual == target
            snapshot = {
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "stock_quantity": actual,
            }
        elif action_id == "amazon.pricing.update":
            actual_value, actual_currency = self._price(remote)
            target_text = str(output.get("target_value") or "")
            target_amount, _, target_currency = target_text.partition(" ")
            matched = (
                actual_value is not None
                and actual_value == Decimal(target_amount)
                and actual_currency == target_currency
            )
            snapshot = {
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "price": float(actual_value) if actual_value is not None else None,
                "currency": actual_currency,
            }
        else:
            return ActionVerification(
                matched=False,
                details={"error": "适配器不支持该动作"},
            )
        return ActionVerification(
            matched=matched,
            terminal=matched,
            snapshot=snapshot,
            details={
                "verification_level": "external_readback",
                "attribute_path": output.get("attribute_path"),
            },
        )
