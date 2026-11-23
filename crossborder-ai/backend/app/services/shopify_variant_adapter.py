"""Shopify 变体改价与库存写回动作适配器。"""

from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.services.action_runtime import ActionExecution, ActionVerification


def _numeric_id(value: str | int | None) -> str:
    normalized = str(value or "").strip().rsplit("/", 1)[-1]
    if not normalized.isdigit():
        raise ValueError("Shopify 资源编号格式不正确")
    return normalized


class ShopifyVariantActionAdapter:
    """通过已发布记录定位远程变体，完成改价或库存写回和回读。"""

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

    async def _context(
        self,
        *,
        target_id: str,
        input_data: dict,
    ) -> tuple[ProductVariant, Product, ShopifyChannel, Publication]:
        try:
            variant_id = UUID(str(target_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("变体编号格式不正确") from exc
        variant = (
            await self.db.execute(
                select(ProductVariant).where(
                    ProductVariant.id == variant_id,
                    ProductVariant.user_id == self.user_id,
                    ProductVariant.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if variant is None:
            raise ValueError("SKU 不存在或不属于当前工作区")
        product = (
            await self.db.execute(
                select(Product).where(
                    Product.id == variant.product_id,
                    Product.user_id == self.user_id,
                    Product.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ValueError("商品不存在或不属于当前工作区")

        publication_query = (
            select(Publication)
            .join(
                ListingDraft,
                Publication.listing_id == ListingDraft.id,
            )
            .where(
                Publication.user_id == self.user_id,
                Publication.platform == "shopify",
                Publication.status == "completed",
                Publication.external_product_id.is_not(None),
                ListingDraft.user_id == self.user_id,
                ListingDraft.workspace_id == self.workspace_id,
                ListingDraft.product_id == product.id,
            )
            .order_by(Publication.created_at.desc())
        )
        if input_data.get("channel_id"):
            publication_query = publication_query.where(
                Publication.channel_id == str(input_data["channel_id"])
            )
        publication = (
            await self.db.execute(publication_query)
        ).scalars().first()
        if publication is None or not publication.channel_id:
            raise ValueError("商品尚无已完成的 Shopify 发布记录")

        try:
            channel_id = UUID(str(publication.channel_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("发布记录中的 Shopify 店铺无效") from exc
        channel = (
            await self.db.execute(
                select(ShopifyChannel).where(
                    ShopifyChannel.id == channel_id,
                    ShopifyChannel.user_id == self.user_id,
                    ShopifyChannel.workspace_id == self.workspace_id,
                    ShopifyChannel.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if channel is None:
            raise ValueError("Shopify 店铺未连接或授权已失效")
        return variant, product, channel, publication

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
        params: dict | None = None,
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
                params=params,
            )
        if response.status_code == 429:
            raise RuntimeError("Shopify 限流，请稍后重试")
        if response.status_code == 401:
            raise ValueError("Shopify 店铺授权已失效")
        if response.status_code >= 400:
            raise RuntimeError(
                f"Shopify 变体动作失败：{response.text[:200]}"
            )
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def _remote_variant(
        self,
        channel: ShopifyChannel,
        publication: Publication,
        local_variant: ProductVariant,
    ) -> tuple[dict, dict]:
        product_id = _numeric_id(publication.external_product_id)
        payload = await self._request(
            channel,
            "GET",
            f"/products/{product_id}.json",
        )
        product = payload.get("product") or {}
        variants = product.get("variants") or []
        remote = next(
            (
                item
                for item in variants
                if str(item.get("sku") or "").strip() == local_variant.sku
            ),
            None,
        )
        if remote is None:
            raise ValueError("Shopify 商品中找不到对应 SKU")
        return product, remote

    async def _locations(self, channel: ShopifyChannel) -> list[dict]:
        payload = await self._request(channel, "GET", "/locations.json")
        locations = payload.get("locations") or []
        if not isinstance(locations, list) or not locations:
            raise ValueError("Shopify 店铺没有可用库存地点")
        return locations

    async def _inventory_level(
        self,
        channel: ShopifyChannel,
        *,
        inventory_item_id: str,
        location_id: str,
    ) -> dict:
        payload = await self._request(
            channel,
            "GET",
            "/inventory_levels.json",
            params={
                "inventory_item_ids": inventory_item_id,
                "location_ids": location_id,
            },
        )
        levels = payload.get("inventory_levels") or []
        if not levels:
            raise ValueError("Shopify 库存水平尚未初始化")
        return levels[0]

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id not in {"pricing.update", "inventory.update"}:
            raise ValueError("适配器不支持该动作")
        local_variant, product, channel, publication = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        remote_product, remote_variant = await self._remote_variant(
            channel,
            publication,
            local_variant,
        )
        if action_id == "pricing.update":
            try:
                new_price = Decimal(str(input_data.get("price"))).quantize(
                    Decimal("0.01")
                )
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("销售价格式不正确") from exc
            if new_price <= 0:
                raise ValueError("销售价必须大于 0")
            old_price = str(remote_variant.get("price") or "")
            return {
                "channel_id": str(channel.id),
                "product_id": str(product.id),
                "variant_id": str(local_variant.id),
                "sku": local_variant.sku,
                "external_product_id": publication.external_product_id,
                "remote_variant_id": str(remote_variant.get("id")),
                "old_price": old_price,
                "new_price": f"{new_price:.2f}",
                "cost_price": local_variant.cost_price,
                "below_cost": (
                    local_variant.cost_price is not None
                    and new_price < Decimal(str(local_variant.cost_price))
                ),
            }

        try:
            new_stock = int(input_data.get("stock_quantity"))
        except (TypeError, ValueError) as exc:
            raise ValueError("库存数量格式不正确") from exc
        if new_stock < 0:
            raise ValueError("库存数量不能小于 0")
        inventory_item_id = _numeric_id(
            remote_variant.get("inventory_item_id")
        )
        if (
            str(remote_variant.get("inventory_management") or "").lower()
            != "shopify"
        ):
            raise ValueError("该 SKU 未由 Shopify 管理库存")
        requested_location = str(input_data.get("location_id") or "").strip()
        locations = await self._locations(channel)
        location = next(
            (
                item
                for item in locations
                if requested_location
                and str(item.get("id")) == requested_location
            ),
            None,
        )
        if location is None:
            location = next(
                (item for item in locations if item.get("primary")),
                next((item for item in locations if item.get("active")), None),
            )
        if location is None:
            raise ValueError("没有可写回的 Shopify 库存地点")
        location_id = _numeric_id(location.get("id"))
        level = await self._inventory_level(
            channel,
            inventory_item_id=inventory_item_id,
            location_id=location_id,
        )
        return {
            "channel_id": str(channel.id),
            "product_id": str(product.id),
            "variant_id": str(local_variant.id),
            "sku": local_variant.sku,
            "external_product_id": publication.external_product_id,
            "remote_variant_id": str(remote_variant.get("id")),
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "location_name": str(location.get("name") or "Primary"),
            "old_stock": int(level.get("available") or 0),
            "new_stock": new_stock,
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
        local_variant, _product, channel, _publication = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        del local_variant
        if action_id == "pricing.update":
            remote_variant_id = snapshot["remote_variant_id"]
            await self._request(
                channel,
                "PUT",
                f"/variants/{remote_variant_id}.json",
                json_data={
                    "variant": {
                        "id": int(remote_variant_id),
                        "price": snapshot["new_price"],
                    }
                },
            )
            external_id = f"variant:{remote_variant_id}"
        else:
            await self._request(
                channel,
                "POST",
                "/inventory_levels/set.json",
                json_data={
                    "inventory_item_id": int(snapshot["inventory_item_id"]),
                    "location_id": int(snapshot["location_id"]),
                    "available": snapshot["new_stock"],
                },
            )
            external_id = (
                f"inventory:{snapshot['inventory_item_id']}:"
                f"{snapshot['location_id']}"
            )
        return ActionExecution(
            external_id=external_id,
            output={
                "input_data": input_data,
                "channel_id": snapshot["channel_id"],
                "external_product_id": snapshot["external_product_id"],
                "remote_variant_id": snapshot["remote_variant_id"],
                "inventory_item_id": snapshot.get("inventory_item_id"),
                "location_id": snapshot.get("location_id"),
                "expected_price": snapshot.get("new_price"),
                "expected_stock": snapshot.get("new_stock"),
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
        input_data = {
            **((output.get("input_data") or {})),
            "channel_id": output.get("channel_id"),
        }
        _variant, _product, channel, publication = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        if action_id == "pricing.update":
            payload = await self._request(
                channel,
                "GET",
                f"/variants/{output.get('remote_variant_id')}.json",
            )
            remote = payload.get("variant") or {}
            actual = str(remote.get("price") or "")
            expected = str(output.get("expected_price") or "")
            matched = Decimal(actual or "0") == Decimal(expected or "0")
            if matched:
                _variant.price = float(Decimal(expected))
            return ActionVerification(
                matched=matched,
                terminal=True,
                snapshot={
                    "variant_id": output.get("remote_variant_id"),
                    "price": actual,
                },
                details={
                    "expected_price": expected,
                    "mismatches": [] if matched else ["price"],
                },
            )

        _remote_product, remote_variant = await self._remote_variant(
            channel,
            publication,
            _variant,
        )
        inventory_item_id = _numeric_id(
            output.get("inventory_item_id")
            or remote_variant.get("inventory_item_id")
        )
        location_id = _numeric_id(output.get("location_id"))
        level = await self._inventory_level(
            channel,
            inventory_item_id=inventory_item_id,
            location_id=location_id,
        )
        actual_stock = int(level.get("available") or 0)
        expected_stock = int(output.get("expected_stock") or 0)
        matched = actual_stock == expected_stock
        if matched:
            _variant.stock_quantity = expected_stock
        return ActionVerification(
            matched=matched,
            terminal=True,
            snapshot={
                "inventory_item_id": inventory_item_id,
                "location_id": location_id,
                "stock": actual_stock,
            },
            details={
                "expected_stock": expected_stock,
                "mismatches": [] if matched else ["stock"],
            },
        )
