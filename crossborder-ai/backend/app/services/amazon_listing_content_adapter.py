"""Amazon Listing 标题、描述与卖点局部更新动作适配器。"""

import json
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
from app.services.listing_service import update_listing_content
from app.services.platform_rules import validate_listing_for_platform


def _language_tag(language: str | None) -> str:
    return {
        "en": "en_US",
        "zh": "zh_CN",
        "ja": "ja_JP",
        "de": "de_DE",
        "fr": "fr_FR",
        "es": "es_ES",
    }.get((language or "en").strip().lower(), "en_US")


def _values(attributes: dict, key: str) -> list[str]:
    items = attributes.get(key) or []
    if not isinstance(items, list):
        return []
    return [
        str(item.get("value") or "")
        for item in items
        if isinstance(item, dict)
    ]


class AmazonListingContentUpdateAdapter:
    """通过 Listings Items PATCH 修改标题、描述和卖点。"""

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

    def _product_type(self, remote: dict) -> str:
        for item in remote.get("summaries") or []:
            if isinstance(item, dict) and item.get("productType"):
                return str(item["productType"])
        raise ValueError("Amazon product type 不能为空")

    def _changes(self, context: dict, input_data: dict) -> dict:
        title = input_data.get("title")
        description = input_data.get("description")
        bullet_points = input_data.get("bullet_points")
        changes = {
            "title": title.strip() if isinstance(title, str) else None,
            "description": (
                description.strip()
                if isinstance(description, str)
                else None
            ),
            "bullet_points": (
                [
                    str(item).strip()
                    for item in bullet_points
                    if str(item).strip()
                ]
                if isinstance(bullet_points, list)
                else None
            ),
        }
        changed_fields = [
            key for key, value in changes.items() if value is not None
        ]
        if not changed_fields:
            raise ValueError("至少需要提供标题、描述或卖点中的一个变更")
        if changes["bullet_points"] == []:
            raise ValueError("卖点列表不能为空")
        validation = validate_listing_for_platform(
            "amazon",
            {
                "title": changes["title"] if changes["title"] is not None else context["listing"].title,
                "description": (
                    changes["description"]
                    if changes["description"] is not None
                    else context["listing"].description
                ),
                "bullet_points": (
                    changes["bullet_points"]
                    if changes["bullet_points"] is not None
                    else json.loads(context["listing"].bullet_points or "[]")
                ),
                "seo_title": context["listing"].seo_title,
                "seo_description": context["listing"].seo_description,
            },
        )
        errors = [
            item["message"]
            for item in validation["checks"]
            if item["status"] == "error"
        ]
        if errors:
            raise ValueError("；".join(errors))
        return {
            "changes": changes,
            "changed_fields": changed_fields,
        }

    def _patches(
        self,
        context: dict,
        changes: dict,
    ) -> list[dict]:
        locale = _language_tag(context["listing"].language)
        marketplace_id = context["marketplace_id"]
        patches: list[dict] = []
        if changes["title"] is not None:
            patches.append(
                {
                    "op": "replace",
                    "path": "/attributes/item_name",
                    "value": [
                        {
                            "value": changes["title"],
                            "language_tag": locale,
                            "marketplace_id": marketplace_id,
                        }
                    ],
                }
            )
        if changes["description"] is not None:
            patches.append(
                {
                    "op": "replace",
                    "path": "/attributes/product_description",
                    "value": [
                        {
                            "value": changes["description"],
                            "language_tag": locale,
                            "marketplace_id": marketplace_id,
                        }
                    ],
                }
            )
        if changes["bullet_points"] is not None:
            patches.append(
                {
                    "op": "replace",
                    "path": "/attributes/bullet_point",
                    "value": [
                        {
                            "value": item,
                            "language_tag": locale,
                            "marketplace_id": marketplace_id,
                        }
                        for item in changes["bullet_points"]
                    ],
                }
            )
        return patches

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "amazon.listings.update":
            raise ValueError("适配器不支持该动作")
        context = await self._context(target_id, input_data)
        remote = await self._remote(context)
        product_type = self._product_type(remote)
        prepared = self._changes(context, input_data)
        patches = self._patches(context, prepared["changes"])
        preview = await self.service.patch_listing(
            refresh_token=context["refresh_token"],
            seller_id=context["connection"].external_account_id,
            marketplace_id=context["marketplace_id"],
            sku=context["variant"].sku,
            product_type=product_type,
            patches=patches,
            preview=True,
        )
        status = str(preview.get("status") or "VALIDATION_PREVIEW").upper()
        if status in {"INVALID", "ERROR"}:
            raise ValueError("Amazon Listing 内容预检未通过")
        return {
            "listing_id": str(context["listing"].id),
            "variant_id": str(context["variant"].id),
            "sku": context["variant"].sku,
            "marketplace_id": context["marketplace_id"],
            "product_type": product_type,
            "changed_fields": prepared["changed_fields"],
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
        product_type = self._product_type(remote)
        prepared = self._changes(context, input_data)
        response = await self.service.patch_listing(
            refresh_token=context["refresh_token"],
            seller_id=context["connection"].external_account_id,
            marketplace_id=context["marketplace_id"],
            sku=context["variant"].sku,
            product_type=product_type,
            patches=self._patches(context, prepared["changes"]),
            preview=False,
        )
        status = str(response.get("status") or "ACCEPTED").upper()
        if status in {"INVALID", "ERROR"}:
            raise RuntimeError("Amazon Listing 内容提交未通过")
        return ActionExecution(
            external_id=str(context["listing"].id),
            output={
                "listing_id": str(context["listing"].id),
                "variant_id": str(context["variant"].id),
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "product_type": product_type,
                "changed_fields": prepared["changed_fields"],
                "changes": prepared["changes"],
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
        if action_id != "amazon.listings.update":
            return ActionVerification(
                matched=False,
                details={"error": "适配器不支持该动作"},
            )
        output = execution.output or {}
        changes = output.get("changes") or {}
        try:
            context = await self._context(
                target_id,
                {
                    "listing_id": output.get("listing_id") or target_id,
                    "variant_id": output.get("variant_id"),
                    "marketplace_id": output.get("marketplace_id"),
                },
            )
            remote = await self._remote(context)
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": str(exc)[:300]},
            )
        attributes = remote.get("attributes") or {}
        remote_title = (_values(attributes, "item_name") or [""])[0]
        remote_description = (
            _values(attributes, "product_description") or [""]
        )[0]
        remote_bullets = _values(attributes, "bullet_point")
        matched = True
        if changes.get("title") is not None:
            matched = matched and remote_title == changes["title"]
        if changes.get("description") is not None:
            matched = matched and remote_description == changes["description"]
        if changes.get("bullet_points") is not None:
            matched = matched and remote_bullets == changes["bullet_points"]
        if not matched:
            return ActionVerification(
                matched=False,
                details={
                    "error": "Amazon Listing 内容回读不一致",
                    "changed_fields": output.get("changed_fields") or [],
                },
            )
        update_listing_content(
            context["listing"],
            title=changes.get("title"),
            description=changes.get("description"),
            bullet_points=changes.get("bullet_points"),
        )
        await self.db.flush()
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "listing_id": str(context["listing"].id),
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "changed_fields": output.get("changed_fields") or [],
                "version": context["listing"].version,
                "compliance_status": context["listing"].compliance_status,
            },
            details={"verification_level": "external_readback"},
        )
