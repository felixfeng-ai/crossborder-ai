"""Amazon Listing 持久图片 URL 绑定动作适配器。"""

import ipaddress
import json
from urllib.parse import parse_qs, urlparse
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


def _validate_image_url(value: str) -> str:
    url = str(value or "").strip()
    if url.startswith("s3://"):
        bucket = url[5:].split("/", 1)[0]
        if not bucket or "/" not in url[5:]:
            raise ValueError("Amazon 图片 S3 URL 格式不正确")
        return url
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Amazon 图片必须是 HTTPS 或 s3:// URL")
    if parsed.username or parsed.password:
        raise ValueError("Amazon 图片 URL 不能包含账号凭据")
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Amazon 图片不能使用 localhost")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    ):
        raise ValueError("Amazon 图片不能使用内网或本机 IP")
    query_keys = {
        key.lower() for key in parse_qs(parsed.query).keys()
    }
    signed_markers = {
        "x-amz-signature",
        "x-amz-credential",
        "signature",
        "sig",
        "expires",
    }
    if query_keys & signed_markers:
        raise ValueError("Amazon 图片不能使用临时签名 URL")
    return url


def _locators(attributes: dict, key: str) -> list[str]:
    items = attributes.get(key) or []
    if not isinstance(items, list):
        return []
    return [
        str(item.get("media_location") or "")
        for item in items
        if isinstance(item, dict)
    ]


class AmazonListingMediaAttachAdapter:
    """把持久图片 URL PATCH 到 Amazon Listing 图片槽位。"""

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

    def _images(self, input_data: dict) -> dict:
        main_image_url = str(
            input_data.get("main_image_url") or ""
        ).strip()
        others = input_data.get("other_image_urls") or []
        if not isinstance(others, list):
            raise ValueError("Amazon 副图必须是 URL 列表")
        normalized_others = [
            _validate_image_url(str(item))
            for item in others
            if str(item).strip()
        ]
        if len(normalized_others) > 8:
            raise ValueError("Amazon 副图最多 8 张")
        if not main_image_url and not normalized_others:
            raise ValueError("至少需要提供一张 Amazon 图片 URL")
        main = _validate_image_url(main_image_url) if main_image_url else ""
        return {"main": main, "others": normalized_others}

    def _patches(self, images: dict, marketplace_id: str) -> list[dict]:
        patches = []
        if images["main"]:
            patches.append(
                {
                    "op": "replace",
                    "path": "/attributes/main_product_image_locator",
                    "value": [
                        {
                            "media_location": images["main"],
                            "marketplace_id": marketplace_id,
                        }
                    ],
                }
            )
        for index, url in enumerate(images["others"], start=1):
            patches.append(
                {
                    "op": "replace",
                    "path": (
                        "/attributes/other_product_image_locator_"
                        f"{index}"
                    ),
                    "value": [
                        {
                            "media_location": url,
                            "marketplace_id": marketplace_id,
                        }
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
        if action_id != "amazon.listing.media.attach":
            raise ValueError("适配器不支持该动作")
        context = await self._context(target_id, input_data)
        remote = await self._remote(context)
        product_type = self._product_type(remote)
        images = self._images(input_data)
        patches = self._patches(images, context["marketplace_id"])
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
            raise ValueError("Amazon Listing 图片预检未通过")
        return {
            "listing_id": str(context["listing"].id),
            "variant_id": str(context["variant"].id),
            "sku": context["variant"].sku,
            "marketplace_id": context["marketplace_id"],
            "product_type": product_type,
            "image_count": len(patches),
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
        images = self._images(input_data)
        response = await self.service.patch_listing(
            refresh_token=context["refresh_token"],
            seller_id=context["connection"].external_account_id,
            marketplace_id=context["marketplace_id"],
            sku=context["variant"].sku,
            product_type=product_type,
            patches=self._patches(images, context["marketplace_id"]),
            preview=False,
        )
        status = str(response.get("status") or "ACCEPTED").upper()
        if status in {"INVALID", "ERROR"}:
            raise RuntimeError("Amazon Listing 图片提交未通过")
        return ActionExecution(
            external_id=str(context["listing"].id),
            output={
                "listing_id": str(context["listing"].id),
                "variant_id": str(context["variant"].id),
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "product_type": product_type,
                "images": images,
                "image_count": len(images["others"]) + (1 if images["main"] else 0),
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
        if action_id != "amazon.listing.media.attach":
            return ActionVerification(
                matched=False,
                details={"error": "适配器不支持该动作"},
            )
        output = execution.output or {}
        images = output.get("images") or {}
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
        main = (_locators(attributes, "main_product_image_locator") or [""])[0]
        others = []
        for index in range(1, 9):
            values = _locators(
                attributes,
                f"other_product_image_locator_{index}",
            )
            if values:
                others.append(values[0])
        matched = (
            (not images.get("main") or main == images["main"])
            and others[: len(images.get("others") or [])]
            == (images.get("others") or [])
        )
        if not matched:
            return ActionVerification(
                matched=False,
                details={
                    "error": "Amazon 尚未返回一致的图片定位器",
                    "main_found": bool(main),
                    "other_found": len(others),
                },
            )
        return ActionVerification(
            matched=True,
            terminal=True,
            snapshot={
                "listing_id": str(context["listing"].id),
                "sku": context["variant"].sku,
                "marketplace_id": context["marketplace_id"],
                "image_count": int(output.get("image_count") or 0),
            },
            details={"verification_level": "external_readback"},
        )
