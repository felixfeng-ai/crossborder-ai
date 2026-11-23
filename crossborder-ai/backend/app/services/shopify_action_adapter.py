"""Shopify 商品发布动作适配器。"""

from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.shopify_publish_service import (
    _load_active_variants,
    build_shopify_product_payload,
    publish_shopify_product,
)


class ShopifyPublishActionAdapter:
    """把统一的 listings.publish 动作映射到现有 Shopify 发布服务。"""

    def __init__(self, db: AsyncSession, *, user_id: UUID):
        self.db = db
        self.user_id = user_id

    async def _load_context(self, input_data: dict):
        """每次预检和执行都重新读取真实商品、Listing 和店铺连接。"""

        try:
            product_id = UUID(str(input_data["product_id"]))
            channel_id = UUID(str(input_data["channel_id"]))
            listing_id = (
                UUID(str(input_data["listing_id"]))
                if input_data.get("listing_id")
                else None
            )
            variant_ids = [
                UUID(str(item))
                for item in input_data.get("variant_ids", [])
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Shopify 发布参数不完整") from exc

        user = await self.db.get(User, self.user_id)
        product = (
            await self.db.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.user_id == self.user_id,
                )
            )
        ).scalar_one_or_none()
        if user is None or product is None:
            raise ValueError("商品不存在或不属于当前用户")

        channel = (
            await self.db.execute(
                select(ShopifyChannel).where(
                    ShopifyChannel.id == channel_id,
                    ShopifyChannel.user_id == self.user_id,
                    ShopifyChannel.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if channel is None:
            raise ValueError("Shopify 店铺未连接或授权已失效")

        listing = None
        if listing_id is not None:
            listing = (
                await self.db.execute(
                    select(ListingDraft).where(
                        ListingDraft.id == listing_id,
                        ListingDraft.user_id == self.user_id,
                        ListingDraft.product_id == product.id,
                    )
                )
            ).scalar_one_or_none()
            if listing is None:
                raise ValueError("Listing 不存在或与商品不匹配")

        variants = await _load_active_variants(
            self.db,
            product,
            self.user_id,
            variant_ids=variant_ids or None,
        )
        return user, product, listing, channel, variants

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        """构建完整 Payload，确认售价、SKU、媒体和店铺授权均可用。"""

        if action_id != "listings.publish":
            raise ValueError("适配器不支持该动作")
        _user, product, listing, channel, variants = await self._load_context(
            input_data
        )
        if str(product.id) != str(target_id):
            raise ValueError("动作目标商品与输入不一致")

        prepared = build_shopify_product_payload(
            product,
            listing,
            variants,
        )
        return {
            "product_id": str(product.id),
            "channel_id": str(channel.id),
            "shop_domain": self._channel_domain(channel),
            "title": prepared.product["title"],
            "status": prepared.product["status"],
            "listing_id": str(listing.id) if listing else None,
            "listing_version": listing.version if listing else None,
            "variant_count": prepared.variant_count,
            "image_count": prepared.image_count,
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        """调用统一发布服务，发布结果由后续回读决定是否真正完成。"""

        if action_id != "listings.publish":
            raise ValueError("适配器不支持该动作")
        user, product, listing, channel, variants = await self._load_context(
            input_data
        )
        if str(product.id) != str(target_id):
            raise ValueError("动作目标商品与输入不一致")

        result = await publish_shopify_product(
            self.db,
            user=user,
            product=product,
            listing=listing,
            channel=channel,
            idempotency_key=idempotency_key,
            variant_ids=[variant.id for variant in variants],
        )
        external_id = result.publication.external_product_id
        if not external_id:
            raise RuntimeError("Shopify 未返回商品编号")
        return ActionExecution(
            external_id=external_id,
            output={
                "publication_id": str(result.publication.id),
                "external_url": result.publication.external_url,
                "input_data": input_data,
                "channel_id": str(channel.id),
                "variants_published": (
                    result.prepared.variant_count
                    if result.prepared is not None
                    else len(variants)
                ),
                "images_published": (
                    result.prepared.image_count
                    if result.prepared is not None
                    else None
                ),
                "replayed": result.replayed,
            },
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        """重新读取 Shopify 商品，避免把 HTTP 201 当成发布完成。"""

        if action_id != "listings.publish" or not execution.external_id:
            return ActionVerification(
                matched=False,
                details={"error": "缺少可回读的 Shopify 商品编号"},
            )

        _user, product, listing, channel, variants = await self._load_context(
            {
                **((execution.output or {}).get("input_data") or {}),
                "product_id": str(target_id),
                "channel_id": (execution.output or {}).get("channel_id"),
            }
        )
        remote = await self._read_remote_product(
            channel,
            execution.external_id,
        )
        prepared = build_shopify_product_payload(product, listing, variants)
        expected_title = prepared.product["title"]
        expected_status = prepared.product["status"]
        mismatches: list[str] = []
        if remote.get("id") != execution.external_id:
            mismatches.append("external_id")
        if remote.get("title") != expected_title:
            mismatches.append("title")
        if remote.get("status") != expected_status:
            mismatches.append("status")
        if len(remote.get("variants") or []) != prepared.variant_count:
            mismatches.append("variant_count")
        return ActionVerification(
            matched=not mismatches,
            snapshot={
                "id": remote.get("id"),
                "title": remote.get("title"),
                "status": remote.get("status"),
                "variant_count": len(remote.get("variants") or []),
            },
            details={
                "expected_title": expected_title,
                "expected_status": expected_status,
                "variant_count": len(remote.get("variants") or []),
                "expected_variant_count": prepared.variant_count,
                "mismatches": mismatches,
            },
        )

    @staticmethod
    def _channel_domain(channel: ShopifyChannel) -> str:
        domain = (channel.shop_domain or "").strip()
        if domain:
            return domain
        return (
            f"{(channel.shop_name or '').replace('.myshopify.com', '').strip()}"
            ".myshopify.com"
        )

    async def _read_remote_product(
        self,
        channel: ShopifyChannel,
        external_id: str,
    ) -> dict:
        """读取 Shopify 商品真实状态；可在测试中替换为确定性响应。"""

        product_id = external_id.rsplit("/", 1)[-1]
        shop_url = (
            f"https://{self._channel_domain(channel)}"
            f"/admin/api/{settings.SHOPIFY_API_VERSION}/products/{product_id}.json"
        )
        headers = {
            "X-Shopify-Access-Token": decrypt_value(channel.access_token),
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(shop_url, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(
                f"Shopify 回读失败：{response.text[:200]}"
            )
        product = response.json().get("product") or {}
        numeric_id = product.get("id")
        return {
            "id": (
                f"gid://shopify/Product/{numeric_id}"
                if numeric_id is not None
                else None
            ),
            "title": product.get("title"),
            "status": product.get("status"),
            "variants": product.get("variants") or [],
        }
