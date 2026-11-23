"""工作区素材发布为公共图片并绑定 Amazon Listing。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_asset import ImageAsset
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.amazon_listing_media_adapter import (
    AmazonListingMediaAttachAdapter,
)
from app.services.public_image_storage import (
    PublicImageStorage,
    get_public_image_storage,
    publish_public_image_asset,
)


class AmazonListingAssetMediaAdapter:
    """按卖家选择顺序公开素材，再写入 Amazon 图片定位器。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        media_service=None,
        public_storage: PublicImageStorage | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.media_storage = AmazonListingMediaAttachAdapter(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            service=media_service,
        )
        self.public_storage = public_storage

    async def _assets(self, input_data: dict) -> list[ImageAsset]:
        raw_ids = input_data.get("asset_ids") or []
        if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= 9:
            raise ValueError("Amazon 图片素材必须提供 1 至 9 张")
        try:
            asset_ids = [UUID(str(item)) for item in raw_ids]
        except (TypeError, ValueError) as exc:
            raise ValueError("Amazon 图片素材编号格式不正确") from exc
        assets = (
            await self.db.execute(
                select(ImageAsset).where(
                    ImageAsset.id.in_(asset_ids),
                    ImageAsset.workspace_id == self.workspace_id,
                    ImageAsset.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        by_id = {item.id: item for item in assets}
        ordered = [by_id[item] for item in asset_ids if item in by_id]
        if len(ordered) != len(asset_ids):
            raise ValueError("Amazon 图片素材不存在或不属于当前工作区")
        if any(not item.content_type.startswith("image/") for item in ordered):
            raise ValueError("Amazon 媒体动作只接受图片素材")
        return ordered

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "amazon.listing.media.attach_assets":
            raise ValueError("适配器不支持该动作")
        assets = await self._assets(input_data)
        await self.media_storage._context(target_id, input_data)
        storage = self.public_storage or get_public_image_storage()
        if storage is None:
            raise ValueError("公共图片托管尚未配置")
        return {
            "listing_id": str(input_data.get("listing_id") or target_id),
            "variant_id": str(input_data.get("variant_id") or ""),
            "marketplace_id": str(
                input_data.get("marketplace_id") or ""
            ),
            "asset_ids": [str(item.id) for item in assets],
            "asset_count": len(assets),
            "public_visibility": True,
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        assets = await self._assets(input_data)
        storage = self.public_storage or get_public_image_storage()
        public_urls = [
            await publish_public_image_asset(item, storage=storage)
            for item in assets
        ]
        media_input = {
            **input_data,
            "main_image_url": public_urls[0],
            "other_image_urls": public_urls[1:],
        }
        await self.media_storage.preflight(
            action_id="amazon.listing.media.attach",
            target_id=target_id,
            input_data=media_input,
        )
        execution = await self.media_storage.execute(
            action_id="amazon.listing.media.attach",
            target_id=target_id,
            input_data=media_input,
            idempotency_key=idempotency_key,
        )
        output = dict(execution.output or {})
        output.update(
            {
                "asset_ids": [str(item.id) for item in assets],
                "asset_count": len(assets),
                "public_urls": public_urls,
            }
        )
        return ActionExecution(
            external_id=execution.external_id,
            output=output,
        )

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        if action_id != "amazon.listing.media.attach_assets":
            return ActionVerification(
                matched=False,
                details={"error": "适配器不支持该动作"},
            )
        verification = await self.media_storage.verify(
            action_id="amazon.listing.media.attach",
            target_id=target_id,
            execution=execution,
        )
        if verification.snapshot is not None:
            verification.snapshot.update(
                {
                    "asset_ids": (execution.output or {}).get(
                        "asset_ids",
                        [],
                    ),
                    "asset_count": (execution.output or {}).get(
                        "asset_count",
                        0,
                    ),
                }
            )
        return verification
