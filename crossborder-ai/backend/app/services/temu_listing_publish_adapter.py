"""Temu V3 商品发布受控动作适配器。"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.workspace import Workspace
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.public_image_storage import (
    PublicImageStorage,
    get_public_image_storage,
)
from app.services.temu_listing_publish import (
    TemuListingPublishService,
    build_temu_listing_payload,
)
from app.services.temu_listing_status_sync import (
    register_temu_listing_submission,
)


REQUIRED_PUBLISH_SCOPES = {
    "temu.local.goods.v3.add",
    "bg.local.goods.list.query",
}


class TemuListingPublishActionAdapter:
    """构建、确认、提交并回读 Temu V3 商品。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        service: TemuListingPublishService | None = None,
        public_storage: PublicImageStorage | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.service = service or TemuListingPublishService(
            db,
            user_id=user_id,
        )
        self.public_storage = public_storage

    async def _assets(self, input_data: dict) -> list[ImageAsset]:
        raw_ids = input_data.get("asset_ids") or []
        if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= 9:
            raise ValueError("Temu 商品图片必须提供 1 至 9 张")
        try:
            asset_ids = [UUID(str(item)) for item in raw_ids]
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu 图片素材编号格式不正确") from exc
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
            raise ValueError("Temu 图片素材不存在或不属于当前工作区")
        supported_types = {"image/jpeg", "image/png", "image/webp"}
        if any(item.content_type not in supported_types for item in ordered):
            raise ValueError("Temu 商品动作只接受 JPG、PNG 或 WebP 图片")
        return ordered

    async def _context(self, target_id: str, input_data: dict) -> dict:
        try:
            listing_id = UUID(
                str(input_data.get("listing_id") or target_id)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu Listing 编号格式不正确") from exc
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
        if listing.compliance_status != "passed":
            raise ValueError("Temu Listing 尚未通过当前版本合规检查")
        product = (
            await self.db.execute(
                select(Product).where(
                    Product.id == listing.product_id,
                    Product.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ValueError("Temu Listing 关联商品不存在")
        variants = (
            await self.db.execute(
                select(ProductVariant)
                .where(
                    ProductVariant.product_id == product.id,
                    ProductVariant.workspace_id == self.workspace_id,
                    ProductVariant.is_active.is_(True),
                )
                .order_by(ProductVariant.created_at, ProductVariant.id)
            )
        ).scalars().all()
        if not variants:
            raise ValueError("Temu 商品缺少可发布 SKU")
        try:
            connection_id = UUID(
                str(input_data.get("connection_id") or "")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Temu 店铺连接 ID 格式不正确") from exc
        workspace = await self.db.get(Workspace, self.workspace_id)
        if workspace is None:
            raise ValueError("工作区不存在")
        connection = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.id == connection_id,
                    PlatformConnection.user_id.in_(
                        {self.user_id, workspace.owner_user_id}
                    ),
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            raise ValueError("Temu 店铺连接不存在或授权不可用")
        try:
            metadata = json.loads(connection.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        store_type = str(metadata.get("store_type") or "").strip().lower()
        if store_type not in {"local", "semi"}:
            raise ValueError("Temu 商品发布只支持 LOCAL/SEMI 店铺")
        scopes = {
            str(item).strip()
            for item in metadata.get("api_scope_list") or []
            if str(item).strip()
        }
        missing = sorted(REQUIRED_PUBLISH_SCOPES - scopes)
        if missing:
            raise ValueError(
                "Temu 商品发布 scope 不完整：" + "、".join(missing)
            )
        assets = await self._assets(input_data)
        category_name = str(
            input_data.get("category_name") or ""
        ).strip()
        currency = str(input_data.get("currency") or "").strip().upper()
        language = str(
            input_data.get("language") or listing.language or "en"
        ).strip()
        attributes = input_data.get("attributes")
        package_info = input_data.get("package_info")
        return {
            "listing": listing,
            "product": product,
            "variants": list(variants),
            "connection": connection,
            "assets": assets,
            "category_name": category_name,
            "currency": currency,
            "language": language,
            "attributes": (
                attributes if isinstance(attributes, list) else []
            ),
            "package_info": (
                package_info if isinstance(package_info, dict) else None
            ),
        }

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "temu.listings.submit":
            raise ValueError("适配器不支持该动作")
        context = await self._context(target_id, input_data)
        storage = self.public_storage or get_public_image_storage()
        if storage is None:
            raise ValueError("公共图片托管尚未配置")
        placeholder_urls = [
            f"https://public.veyaship.invalid/{asset.id}.jpg"
            for asset in context["assets"]
        ]
        payload = build_temu_listing_payload(
            context["product"],
            context["listing"],
            context["variants"],
            image_urls=placeholder_urls,
            category_name=context["category_name"],
            currency=context["currency"],
            language=context["language"],
            attributes=context["attributes"],
            package_info=context["package_info"],
        )
        return {
            "listing_id": str(context["listing"].id),
            "listing_version": context["listing"].version,
            "product_id": str(context["product"].id),
            "connection_id": str(context["connection"].id),
            "asset_ids": [str(item.id) for item in context["assets"]],
            "asset_count": len(context["assets"]),
            "sku_count": len(payload["skuList"]),
            "item_count": sum(
                int(item["quantity"])
                for item in payload["skuList"]
            ),
            "category_name": context["category_name"],
            "currency": context["currency"],
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
        storage = self.public_storage or get_public_image_storage()
        public_urls = [
            await self.service.publish_asset(asset, storage=storage)
            for asset in context["assets"]
        ]
        payload = build_temu_listing_payload(
            context["product"],
            context["listing"],
            context["variants"],
            image_urls=public_urls,
            category_name=context["category_name"],
            currency=context["currency"],
            language=context["language"],
            attributes=context["attributes"],
            package_info=context["package_info"],
        )
        result = await self.service.submit(
            connection_id=context["connection"].id,
            payload=payload,
        )
        return ActionExecution(
            external_id=str(result["goods_id"]),
            output={
                "listing_id": str(context["listing"].id),
                "listing_version": context["listing"].version,
                "connection_id": str(context["connection"].id),
                "external_goods_id": result["external_goods_id"],
                "goods_id": result["goods_id"],
                "public_urls": public_urls,
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
        if action_id != "temu.listings.submit":
            raise ValueError("适配器不支持该动作")
        output = execution.output or {}
        try:
            connection_id = UUID(str(output["connection_id"]))
            goods_id = int(output["goods_id"])
            external_goods_id = str(output["external_goods_id"])
            remote = await self.service.read_product(
                connection_id=connection_id,
                goods_id=goods_id,
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        if remote is None:
            return ActionVerification(
                matched=False,
                details={"error": "Temu 尚未回读该商品"},
            )
        remote_external_id = str(
            remote.get("external_goods_id") or ""
        )
        if (
            remote_external_id
            and remote_external_id != external_goods_id
        ):
            return ActionVerification(
                matched=False,
                details={"error": "Temu 回读的外部商品 ID 不一致"},
            )
        tracking_registered = True
        tracking_error = None
        try:
            await register_temu_listing_submission(
                self.db,
                workspace_id=self.workspace_id,
                actor_user_id=self.user_id,
                connection_id=connection_id,
                listing_id=UUID(str(output["listing_id"])),
                goods_id=goods_id,
                external_goods_id=external_goods_id,
                raw_status=remote.get("status"),
                raw_sub_status=remote.get("sub_status"),
            )
        except Exception as exc:
            tracking_registered = False
            tracking_error = str(exc)[:300]
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "goods_id": goods_id,
                "external_goods_id": remote_external_id,
                "raw_status": remote.get("status"),
                "raw_sub_status": remote.get("sub_status"),
                "state": "submitted_processing",
            },
            details={
                "verification_level": "platform_readback",
                "status_mapping": "not_guessed",
                "tracking_registered": tracking_registered,
                "tracking_error": tracking_error,
            },
        )
