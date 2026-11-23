"""把已生成图片附加到 Shopify 商品的动作适配器。"""

import base64
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.services.action_runtime import ActionExecution, ActionVerification


class ShopifyListingMediaActionAdapter:
    """使用 base64 上传私有图片，并通过 alt 幂等标记回读。"""

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
    ) -> tuple[
        ListingDraft,
        Product,
        ShopifyChannel,
        Publication,
        list[ImageAsset],
    ]:
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
        publication_query = (
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
            publication_query = publication_query.where(
                Publication.channel_id == str(input_data["channel_id"])
            )
        publication = (
            await self.db.execute(publication_query)
        ).scalars().first()
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

        try:
            asset_ids = list(
                dict.fromkeys(
                    UUID(str(value))
                    for value in input_data.get("asset_ids") or []
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("图片素材编号格式不正确") from exc
        if not asset_ids or len(asset_ids) > 4:
            raise ValueError("每次必须选择 1 至 4 张图片")
        assets = (
            await self.db.execute(
                select(ImageAsset).where(
                    ImageAsset.id.in_(asset_ids),
                    ImageAsset.user_id == self.user_id,
                    ImageAsset.workspace_id == self.workspace_id,
                )
            )
        ).scalars().all()
        asset_by_id = {asset.id: asset for asset in assets}
        ordered_assets = [
            asset_by_id[asset_id]
            for asset_id in asset_ids
            if asset_id in asset_by_id
        ]
        if len(ordered_assets) != len(asset_ids):
            raise ValueError("图片素材不存在或不属于当前工作区")
        return listing, product, channel, publication, ordered_assets

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
            timeout=30,
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
                f"Shopify 商品图片上传失败：{response.text[:200]}"
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

    def _asset_path(self, asset: ImageAsset) -> Path:
        root = Path(settings.IMAGE_STORAGE_DIR).resolve()
        target = (root / asset.storage_key).resolve()
        if target != root and root not in target.parents:
            raise ValueError("图片素材路径非法")
        if not target.is_file():
            raise ValueError("图片素材文件不存在")
        if target.stat().st_size > settings.MAX_IMAGE_UPLOAD_BYTES:
            raise ValueError("图片素材文件过大")
        return target

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "listing.media.attach":
            raise ValueError("适配器不支持该动作")
        listing, product, channel, publication, assets = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        for asset in assets:
            self._asset_path(asset)
        remote = await self._remote_product(
            channel,
            publication.external_product_id or "",
        )
        return {
            "channel_id": str(channel.id),
            "listing_id": str(listing.id),
            "product_id": str(product.id),
            "external_product_id": publication.external_product_id,
            "asset_count": len(assets),
            "asset_ids": [str(asset.id) for asset in assets],
            "asset_names": [asset.name for asset in assets],
            "existing_image_count": len(remote.get("images") or []),
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
        _listing, _product, channel, _publication, assets = await self._context(
            target_id=target_id,
            input_data=input_data,
        )
        remote = await self._remote_product(
            channel,
            snapshot["external_product_id"],
        )
        existing_alts = {
            str(image.get("alt") or "")
            for image in remote.get("images") or []
        }
        product_id = str(snapshot["external_product_id"]).rsplit("/", 1)[-1]
        marker = f"VeyaShip media {idempotency_key}"[:420]
        expected_alts: list[str] = []
        uploaded_count = 0
        for index, asset in enumerate(assets):
            alt = f"{marker}:{index}"
            expected_alts.append(alt)
            if alt in existing_alts:
                continue
            content = self._asset_path(asset).read_bytes()
            await self._request(
                channel,
                "POST",
                f"/products/{product_id}/images.json",
                json_data={
                    "image": {
                        "attachment": base64.b64encode(content).decode("ascii"),
                        "filename": asset.name,
                        "alt": alt,
                    }
                },
            )
            uploaded_count += 1
        return ActionExecution(
            external_id=f"gid://shopify/Product/{product_id}",
            output={
                "channel_id": snapshot["channel_id"],
                "listing_id": snapshot["listing_id"],
                "product_id": snapshot["product_id"],
                "external_product_id": snapshot["external_product_id"],
                "input_data": input_data,
                "expected_alts": expected_alts,
                "uploaded_count": uploaded_count,
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
        listing, _product, channel, _publication, assets = await self._context(
            target_id=target_id,
            input_data={
                **((output.get("input_data") or {})),
                "channel_id": output.get("channel_id"),
            },
        )
        remote = await self._remote_product(
            channel,
            output.get("external_product_id") or "",
        )
        remote_alts = {
            str(image.get("alt") or "")
            for image in remote.get("images") or []
        }
        expected_alts = output.get("expected_alts") or []
        mismatches = [
            alt for alt in expected_alts if alt not in remote_alts
        ]
        matched = not mismatches
        if matched and assets:
            listing.main_image_url = (
                f"/api/v1/images/assets/{assets[0].id}/file"
            )
        return ActionVerification(
            matched=matched,
            terminal=True,
            snapshot={
                "external_product_id": output.get("external_product_id"),
                "image_count": len(remote.get("images") or []),
            },
            details={
                "mismatches": mismatches,
                "expected_image_count": len(expected_alts),
            },
        )
