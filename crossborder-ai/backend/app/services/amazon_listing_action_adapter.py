"""Amazon Listings Items 移动 Agent 发布动作适配器。"""

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.workspace import Workspace
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.amazon_listing_publish import (
    AmazonListingPublishError,
    AmazonListingPublishService,
    build_amazon_listing_payload,
)


def _issues(value) -> list[dict]:
    return [item for item in value or [] if isinstance(item, dict)]


class AmazonListingPublishActionAdapter:
    """通过卖家已授权的 SP-API 发布 Amazon Listing 并强制回读。"""

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
            raise ValueError("Amazon Listing 尚未通过当前版本合规检查")
        product = (
            await self.db.execute(
                select(Product).where(
                    Product.id == listing.product_id,
                    Product.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ValueError("Amazon Listing 关联商品不存在")

        variant_query = select(ProductVariant).where(
            ProductVariant.product_id == product.id,
            ProductVariant.workspace_id == self.workspace_id,
            ProductVariant.is_active.is_(True),
        )
        if input_data.get("variant_id"):
            try:
                variant_id = UUID(str(input_data["variant_id"]))
            except (TypeError, ValueError) as exc:
                raise ValueError("Amazon 变体编号格式不正确") from exc
            variant_query = variant_query.where(
                ProductVariant.id == variant_id
            )
        else:
            variant_query = variant_query.order_by(
                ProductVariant.created_at
            ).limit(1)
        variant = (
            await self.db.execute(variant_query)
        ).scalar_one_or_none()
        if variant is None:
            raise ValueError("Amazon Listing 缺少可发布 SKU")

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

        product_type = str(
            input_data.get("product_type") or ""
        ).strip()
        if not product_type:
            raise ValueError("Amazon product type 不能为空")
        additional_attributes = input_data.get("additional_attributes")
        payload = build_amazon_listing_payload(
            product,
            listing,
            variant,
            product_type=product_type,
            marketplace_id=marketplace_id,
            language_tag=input_data.get("language_tag"),
            currency=str(input_data.get("currency") or "USD"),
            additional_attributes=(
                additional_attributes
                if isinstance(additional_attributes, dict)
                else None
            ),
        )
        return {
            "listing": listing,
            "product": product,
            "variant": variant,
            "connection": connection,
            "refresh_token": refresh_token,
            "seller_id": connection.external_account_id,
            "marketplace_id": marketplace_id,
            "product_type": product_type,
            "payload": payload,
        }

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id != "amazon.listings.publish":
            raise ValueError("适配器不支持该动作")
        context = await self._context(target_id, input_data)
        try:
            preview = await self.service.submit_listing(
                refresh_token=context["refresh_token"],
                seller_id=context["seller_id"],
                marketplace_id=context["marketplace_id"],
                sku=context["variant"].sku,
                payload=context["payload"],
                preview=True,
            )
        except AmazonListingPublishError as exc:
            raise ValueError(str(exc)) from exc
        issues = _issues(preview.get("issues"))
        preview_status = str(preview.get("status") or "VALIDATION_PREVIEW")
        if preview_status.upper() in {"INVALID", "ERROR"}:
            raise ValueError(
                f"Amazon Listing 预检未通过：{preview_status}"
            )
        return {
            "listing_id": str(context["listing"].id),
            "listing_version": context["listing"].version,
            "product_id": str(context["product"].id),
            "variant_id": str(context["variant"].id),
            "sku": context["variant"].sku,
            "marketplace_id": context["marketplace_id"],
            "product_type": context["product_type"],
            "preview_status": preview_status,
            "issue_count": len(issues),
            "issues": issues[:20],
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
        try:
            response = await self.service.submit_listing(
                refresh_token=context["refresh_token"],
                seller_id=context["seller_id"],
                marketplace_id=context["marketplace_id"],
                sku=context["variant"].sku,
                payload=context["payload"],
                preview=False,
            )
        except AmazonListingPublishError as exc:
            raise RuntimeError(str(exc)) from exc
        issues = _issues(response.get("issues"))
        status = str(response.get("status") or "ACCEPTED")
        if status.upper() in {"INVALID", "ERROR"}:
            raise RuntimeError(
                f"Amazon Listing 提交未通过：{status}"
            )
        external_id = (
            str(response.get("submissionId") or "").strip()
            or f"amazon:{context['marketplace_id']}:{context['variant'].sku}"
        )
        return ActionExecution(
            external_id=external_id,
            output={
                "submission_id": external_id,
                "status": status,
                "sku": context["variant"].sku,
                "variant_id": str(context["variant"].id),
                "marketplace_id": context["marketplace_id"],
                "product_type": context["product_type"],
                "listing_id": str(context["listing"].id),
                "listing_version": context["listing"].version,
                "issue_count": len(issues),
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
            listing_id = UUID(str(output["listing_id"]))
            context = await self._context(
                str(listing_id),
                {
                    "listing_id": str(listing_id),
                    "variant_id": output.get("variant_id"),
                    "marketplace_id": output.get("marketplace_id"),
                    "product_type": output.get("product_type"),
                },
            )
        except Exception:
            # 输出没有完整内部参数时，从当前 Listing 重新解析。
            listing = await self.db.get(ListingDraft, UUID(str(target_id)))
            if listing is None:
                return ActionVerification(
                    matched=False,
                    details={"error": "回读找不到 Amazon Listing"},
                )
            try:
                context = await self._context(
                    str(target_id),
                    {
                        "listing_id": str(target_id),
                        "marketplace_id": output.get("marketplace_id"),
                        "product_type": output.get("product_type"),
                    },
                )
            except Exception as exc:
                return ActionVerification(
                    matched=False,
                    details={"error": str(exc)[:300]},
                )
        try:
            remote = await self.service.get_listing(
                refresh_token=context["refresh_token"],
                seller_id=context["seller_id"],
                marketplace_id=context["marketplace_id"],
                sku=context["variant"].sku,
            )
        except Exception as exc:
            return ActionVerification(
                matched=False,
                details={"error": f"Amazon 回读失败：{str(exc)[:300]}"},
            )
        if remote is None:
            return ActionVerification(
                matched=False,
                details={"error": "Amazon 尚未返回该 Listing"},
            )
        summaries = [
            item
            for item in remote.get("summaries") or []
            if isinstance(item, dict)
            and item.get("marketplaceId") == context["marketplace_id"]
        ]
        if not summaries:
            return ActionVerification(
                matched=False,
                details={"error": "Amazon 回读缺少对应 Marketplace"},
            )
        summary = summaries[0]
        statuses = [
            str(item) for item in summary.get("status") or []
        ]
        terminal = (
            "BUYABLE" in statuses
            and "DISCOVERABLE" in statuses
        )
        if terminal:
            context["listing"].status = "published"
            context["listing"].published_at = datetime.now(timezone.utc)
        return ActionVerification(
            matched=True,
            terminal=terminal,
            snapshot={
                "sku": remote.get("sku") or context["variant"].sku,
                "asin": summary.get("asin"),
                "marketplace_id": summary.get("marketplaceId"),
                "product_type": summary.get("productType"),
                "status": statuses,
                "issues": _issues(remote.get("issues"))[:20],
            },
            details={
                "verification_level": "external_readback",
                "terminal_status": terminal,
            },
        )
