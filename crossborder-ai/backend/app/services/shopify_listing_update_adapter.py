"""已发布 Shopify 商品内容更新适配器。"""

from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.listing_service import update_listing_content


class ShopifyListingUpdateAdapter:
    """修改已上架商品标题、描述和状态，并回读平台结果。"""

    ALLOWED_STATUS = {"active", "draft", "archived"}

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
    ) -> tuple[ListingDraft, Product, ShopifyChannel, Publication]:
        try:
            listing_id = UUID(str(target_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Listing 编号格式不正确") from exc
        listing = (
            await self.db.execute(
                select(ListingDraft).where(
                    ListingDraft.id == listing_id,
                    ListingDraft.user_id == self.user_id,
                    ListingDraft.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if listing is None:
            raise ValueError("Listing 不存在或不属于当前工作区")
        product = (
            await self.db.execute(
                select(Product).where(
                    Product.id == listing.product_id,
                    Product.user_id == self.user_id,
                    Product.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ValueError("Listing 关联商品不存在")
        query = (
            select(Publication)
            .where(
                Publication.user_id == self.user_id,
                Publication.listing_id == listing.id,
                Publication.platform == "shopify",
                Publication.status == "completed",
                Publication.external_product_id.is_not(None),
            )
            .order_by(Publication.created_at.desc())
        )
        if input_data.get("channel_id"):
            query = query.where(
                Publication.channel_id == str(input_data["channel_id"])
            )
        publication = (await self.db.execute(query)).scalars().first()
        if publication is None or not publication.channel_id:
            raise ValueError("Listing 尚无已完成的 Shopify 发布记录")
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
        return listing, product, channel, publication

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
                f"Shopify 商品更新失败：{response.text[:200]}"
            )
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    async def _remote_product(
        self,
        channel: ShopifyChannel,
        external_product_id: str,
    ) -> dict:
        product_id = str(external_product_id).rsplit("/", 1)[-1]
        if not product_id.isdigit():
            raise ValueError("Shopify 商品编号格式不正确")
        payload = await self._request(
            channel,
            "GET",
            f"/products/{product_id}.json",
        )
        return payload.get("product") or {}

    @classmethod
    def _changes(cls, input_data: dict) -> dict:
        changes: dict = {}
        if "title" in input_data:
            title = str(input_data.get("title") or "").strip()
            if not title or len(title) > 500:
                raise ValueError("商品标题必须为 1 至 500 个字符")
            changes["title"] = title
        if "description" in input_data:
            description = str(input_data.get("description") or "")
            if len(description) > 100_000:
                raise ValueError("商品描述过长")
            changes["description"] = description
        if "status" in input_data:
            status = str(input_data.get("status") or "").strip().lower()
            if status not in cls.ALLOWED_STATUS:
                raise ValueError("商品状态只支持 active、draft 或 archived")
            changes["status"] = status
        if not changes:
            raise ValueError("至少修改标题、描述或状态中的一项")
        return changes

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "listings.update":
            raise ValueError("适配器不支持该动作")
        listing, product, channel, publication = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        changes = self._changes(input_data)
        remote = await self._remote_product(
            channel,
            publication.external_product_id or "",
        )
        return {
            "channel_id": str(channel.id),
            "listing_id": str(listing.id),
            "product_id": str(product.id),
            "external_product_id": publication.external_product_id,
            "before": {
                "title": remote.get("title"),
                "description": remote.get("body_html"),
                "status": remote.get("status"),
            },
            "changes": changes,
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
        _listing, _product, channel, _publication = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        product_payload: dict = {}
        if "title" in snapshot["changes"]:
            product_payload["title"] = snapshot["changes"]["title"]
        if "description" in snapshot["changes"]:
            product_payload["body_html"] = snapshot["changes"]["description"]
        if "status" in snapshot["changes"]:
            product_payload["status"] = snapshot["changes"]["status"]
        product_id = str(snapshot["external_product_id"]).rsplit("/", 1)[-1]
        await self._request(
            channel,
            "PUT",
            f"/products/{product_id}.json",
            json_data={"product": product_payload},
        )
        return ActionExecution(
            external_id=f"gid://shopify/Product/{product_id}",
            output={
                "channel_id": snapshot["channel_id"],
                "listing_id": snapshot["listing_id"],
                "product_id": snapshot["product_id"],
                "external_product_id": snapshot["external_product_id"],
                "input_data": input_data,
                "before": snapshot["before"],
                "expected": snapshot["changes"],
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
        listing, _product, channel, _publication = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        remote = await self._remote_product(
            channel,
            output.get("external_product_id") or "",
        )
        expected = output.get("expected") or {}
        actual = {
            "title": remote.get("title"),
            "description": remote.get("body_html"),
            "status": remote.get("status"),
        }
        mismatches = [
            key for key, value in expected.items() if actual.get(key) != value
        ]
        matched = not mismatches
        if matched and ("title" in expected or "description" in expected):
            update_listing_content(
                listing,
                title=expected.get("title"),
                description=expected.get("description"),
            )
            # 远程内容已经生效；本地保留发布状态，但合规结果需要重新确认。
            listing.status = "published"
        return ActionVerification(
            matched=matched,
            terminal=True,
            snapshot={
                "external_product_id": output.get("external_product_id"),
                **actual,
            },
            details={
                "expected": expected,
                "mismatches": mismatches,
            },
        )
