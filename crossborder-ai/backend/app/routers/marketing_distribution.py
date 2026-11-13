"""营销活动平台发布与效果数据回流。"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.core.crypto import decrypt_value
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import (
    MarketingCampaignPublication,
    MarketingPerformanceSnapshot,
)
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.platform_connection import PlatformConnection
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.routers.marketing_campaigns import get_owned_campaign
from app.services.listing_service import persist_generated_listing
from app.services.ads_metric_import import (
    AdsMetricImportError,
    parse_ad_metrics_csv,
)
from app.services.amazon_listing_publish import (
    AmazonListingPublishError,
    AmazonListingPublishService,
    build_amazon_listing_payload,
)
from app.services.marketing_optimization import (
    build_optimization_asset_actions,
    evaluate_campaign_ab_performance,
    evaluate_variant_performance,
)
from app.services.automation_settings import (
    automation_enabled_for_user,
    record_task_state,
)
from app.services.ip_risk import (
    ensure_ip_report_for_publish,
    ip_publish_block_reason,
)
from app.services.shopify_publish_service import (
    ShopifyPublishError,
    publish_shopify_product,
)
from app.services.publication_service import (
    create_publication,
    find_publication_by_idempotency,
)


router = APIRouter(prefix="/marketing-campaigns", tags=["营销 Agent"])

SUPPORTED_PUBLISH_PLATFORMS = {"shopify", "amazon"}


class CampaignPublicationRequest(BaseModel):
    platform: str
    copy_id: Optional[str] = None
    channel_id: Optional[str] = None
    variant_ids: list[str] = Field(default_factory=list)
    variant_id: Optional[str] = None
    product_type: str = ""
    marketplace_id: Optional[str] = None
    language_tag: Optional[str] = None
    currency: str = "USD"
    additional_attributes: dict = Field(default_factory=dict)
    preview: bool = False


class PerformanceSnapshotInput(BaseModel):
    platform: str
    source: str = "manual"
    copy_id: Optional[str] = None
    period_start: datetime
    period_end: datetime
    impressions: int = Field(0, ge=0)
    clicks: int = Field(0, ge=0)
    orders: int = Field(0, ge=0)
    conversions: int = Field(0, ge=0)
    spend: float = Field(0, ge=0)
    revenue: float = Field(0, ge=0)
    currency: str = Field("USD", min_length=3, max_length=10)
    metadata: dict = Field(default_factory=dict)


class PerformanceImportRequest(BaseModel):
    items: list[PerformanceSnapshotInput] = Field(..., min_length=1)


class AdMetricCsvImportRequest(BaseModel):
    provider: str
    period_start: datetime
    period_end: datetime
    copy_id: Optional[str] = None
    csv_text: str = Field(..., min_length=1, max_length=2_000_000)


def _serialize_publication(record: MarketingCampaignPublication) -> dict:
    return {
        "id": str(record.id),
        "campaign_id": str(record.campaign_id),
        "copy_id": str(record.copy_id) if record.copy_id else None,
        "listing_id": str(record.listing_id) if record.listing_id else None,
        "publication_id": (
            str(record.publication_id) if record.publication_id else None
        ),
        "platform": record.platform,
        "channel_id": record.channel_id,
        "status": record.status,
        "external_product_id": record.external_product_id,
        "external_url": record.external_url,
        "error": record.error,
        "created_at": str(record.created_at),
        "updated_at": str(record.updated_at),
    }


def _serialize_snapshot(snapshot: MarketingPerformanceSnapshot) -> dict:
    try:
        metadata = json.loads(snapshot.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return {
        "id": str(snapshot.id),
        "platform": snapshot.platform,
        "source": snapshot.source,
        "copy_id": str(snapshot.copy_id) if snapshot.copy_id else None,
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "impressions": snapshot.impressions,
        "clicks": snapshot.clicks,
        "orders": snapshot.orders,
        "conversions": snapshot.conversions,
        "spend": snapshot.spend,
        "revenue": snapshot.revenue,
        "currency": snapshot.currency,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": str(snapshot.created_at),
    }


def _aggregate_performance(snapshots: list[MarketingPerformanceSnapshot]) -> dict:
    totals = {
        "impressions": sum(item.impressions for item in snapshots),
        "clicks": sum(item.clicks for item in snapshots),
        "orders": sum(item.orders for item in snapshots),
        "conversions": sum(item.conversions for item in snapshots),
        "spend": round(sum(item.spend for item in snapshots), 2),
        "revenue": round(sum(item.revenue for item in snapshots), 2),
    }
    totals["ctr"] = (
        round(totals["clicks"] / totals["impressions"] * 100, 2)
        if totals["impressions"]
        else 0
    )
    totals["cvr"] = (
        round(totals["orders"] / totals["clicks"] * 100, 2)
        if totals["clicks"]
        else 0
    )
    totals["roas"] = (
        round(totals["revenue"] / totals["spend"], 2)
        if totals["spend"]
        else 0
    )
    return totals


async def _owned_copy(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    copy_id: uuid.UUID,
    user_id,
) -> MarketingCopyAsset | None:
    return (
        await db.execute(
            select(MarketingCopyAsset).where(
                MarketingCopyAsset.id == copy_id,
                MarketingCopyAsset.campaign_id == campaign_id,
                MarketingCopyAsset.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def _resolve_metric_copy(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    copy_id: str | None,
    user_id,
) -> MarketingCopyAsset | None:
    """校验效果数据绑定的文案必须属于当前活动。"""
    if not copy_id:
        return None
    try:
        parsed_id = uuid.UUID(copy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="文案 ID 无效")
    asset = await _owned_copy(db, campaign_id, parsed_id, user_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="文案不存在")
    return asset


@router.get("/{campaign_id}/publications")
async def list_campaign_publications(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    records = (
        await db.execute(
            select(MarketingCampaignPublication)
            .where(
                MarketingCampaignPublication.user_id == current_user.id,
                MarketingCampaignPublication.campaign_id == campaign.id,
            )
            .order_by(desc(MarketingCampaignPublication.created_at))
            .limit(100)
        )
    ).scalars().all()
    return {
        "total": len(records),
        "items": [_serialize_publication(item) for item in records],
    }


@router.post("/{campaign_id}/publications", status_code=201)
async def publish_campaign_copy(
    campaign_id: str,
    payload: CampaignPublicationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    if not check_feature_access(current_user, "shopify_publish"):
        raise HTTPException(status_code=403, detail="活动发布仅限 Standard 及以上套餐使用")
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    platform = payload.platform.strip().lower()
    if platform not in SUPPORTED_PUBLISH_PLATFORMS:
        raise HTTPException(status_code=400, detail="暂不支持该发布平台")

    if idempotency_key:
        existing = (
            await db.execute(
                select(MarketingCampaignPublication).where(
                    MarketingCampaignPublication.user_id == current_user.id,
                    MarketingCampaignPublication.campaign_id == campaign.id,
                    MarketingCampaignPublication.platform == platform,
                    MarketingCampaignPublication.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _serialize_publication(existing)

    if platform == "amazon":
        if (
            not payload.copy_id
            or not payload.channel_id
            or not payload.product_type.strip()
        ):
            raise HTTPException(
                status_code=400,
                detail="Amazon 发布需要文案、卖家连接和 product type",
            )
        try:
            copy_uuid = uuid.UUID(payload.copy_id)
            channel_uuid = uuid.UUID(payload.channel_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Amazon 文案或连接 ID 无效")
        copy_asset = await _owned_copy(
            db,
            campaign.id,
            copy_uuid,
            current_user.id,
        )
        if copy_asset is None:
            raise HTTPException(status_code=404, detail="文案不存在")
        if copy_asset.platform != "amazon":
            raise HTTPException(status_code=400, detail="请选择 Amazon 平台文案")
        if copy_asset.compliance_status != "pass":
            raise HTTPException(status_code=409, detail="文案未通过合规检查")
        if not campaign.product_id:
            raise HTTPException(status_code=409, detail="活动尚未绑定商品")
        product = await db.get(Product, campaign.product_id)
        if product is None or product.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="活动商品不存在")
        connection = (
            await db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.id == channel_uuid,
                    PlatformConnection.user_id == current_user.id,
                    PlatformConnection.platform == "amazon",
                    PlatformConnection.status == "active",
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            raise HTTPException(status_code=404, detail="Amazon 卖家连接不存在或未启用")
        variant_query = select(ProductVariant).where(
            ProductVariant.product_id == product.id,
            ProductVariant.user_id == current_user.id,
            ProductVariant.is_active.is_(True),
        )
        if payload.variant_id:
            try:
                variant_uuid = uuid.UUID(payload.variant_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="SKU 变体 ID 无效")
            variant_query = variant_query.where(ProductVariant.id == variant_uuid)
        variant = (
            await db.execute(
                variant_query.order_by(ProductVariant.created_at, ProductVariant.id)
            )
        ).scalars().first()
        if variant is None:
            raise HTTPException(status_code=409, detail="Amazon 发布至少需要一个启用 SKU")
        marketplace_id = (
            payload.marketplace_id
            or connection.marketplace_id
            or ""
        ).strip()
        if not marketplace_id:
            raise HTTPException(status_code=409, detail="Amazon 卖家连接缺少 Marketplace ID")
        try:
            violations = json.loads(copy_asset.violations_json or "[]")
        except (json.JSONDecodeError, TypeError):
            violations = []
        listing = await persist_generated_listing(
            db,
            user=current_user,
            product=product,
            platform="amazon",
            language=copy_asset.language,
            tone="marketing",
            title=copy_asset.headline,
            description=copy_asset.body,
            bullet_points=[],
            seo_title=copy_asset.headline[:200],
            seo_description=copy_asset.body[:160],
            violations=violations if isinstance(violations, list) else [],
            blocked=False,
            ai_model_used=copy_asset.model_used or "marketing-copy",
        )
        ip_report = await ensure_ip_report_for_publish(
            db,
            user=current_user,
            product=product,
            listing=listing,
            platform="amazon",
        )
        await db.commit()
        ip_block_reason = ip_publish_block_reason(ip_report)
        if ip_block_reason:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "IP 高风险，暂不能发布到 Amazon"
                        if ip_block_reason == "high_risk"
                        else "IP 初筛未完成必要检查，暂不能发布到 Amazon"
                    ),
                    "reason": ip_block_reason,
                    "ip_risk_report_id": ip_report["report_id"],
                    "risks": ip_report["risks"],
                },
            )
        try:
            credentials = json.loads(decrypt_value(connection.credentials))
            refresh_token = str(credentials.get("refresh_token") or "")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Amazon 授权凭据无法读取") from exc
        if not refresh_token:
            raise HTTPException(status_code=409, detail="Amazon 授权缺少 Refresh Token")
        try:
            payload_body = build_amazon_listing_payload(
                product,
                listing,
                variant,
                product_type=payload.product_type,
                marketplace_id=marketplace_id,
                language_tag=payload.language_tag,
                currency=payload.currency,
                additional_attributes=payload.additional_attributes,
            )
            submit_result = await AmazonListingPublishService().submit_listing(
                refresh_token=refresh_token,
                seller_id=connection.external_account_id,
                marketplace_id=marketplace_id,
                sku=variant.sku,
                payload=payload_body,
                preview=payload.preview,
            )
        except AmazonListingPublishError as exc:
            if not payload.preview:
                record = MarketingCampaignPublication(
                    user_id=current_user.id,
                    campaign_id=campaign.id,
                    copy_id=copy_asset.id,
                    listing_id=listing.id,
                    platform="amazon",
                    channel_id=payload.channel_id,
                    status="failed",
                    error=str(exc),
                    idempotency_key=idempotency_key or None,
                )
                db.add(record)
                await db.commit()
            raise HTTPException(
                status_code=exc.status_code,
                detail={"message": str(exc), "issues": exc.issues},
            ) from exc

        issues = submit_result.get("issues") or []
        if payload.preview:
            return {
                "status": submit_result.get("status") or "VALID",
                "submission_id": submit_result.get("submissionId"),
                "sku": variant.sku,
                "issues": issues,
            }
        blocking_issues = [
            item
            for item in issues
            if str(item.get("severity") or "").upper() == "ERROR"
        ]
        submission_status = str(submit_result.get("status") or "").upper()
        if blocking_issues or submission_status in {"INVALID", "REJECTED"}:
            error = "Amazon Listing 校验未通过"
            record = MarketingCampaignPublication(
                user_id=current_user.id,
                campaign_id=campaign.id,
                copy_id=copy_asset.id,
                listing_id=listing.id,
                platform="amazon",
                channel_id=payload.channel_id,
                status="failed",
                error=error,
                idempotency_key=idempotency_key or None,
            )
            db.add(record)
            await db.commit()
            raise HTTPException(
                status_code=409,
                detail={"message": error, "issues": issues},
            )

        existing_publication = await find_publication_by_idempotency(
            db,
            current_user.id,
            "amazon",
            idempotency_key,
        )
        publication = existing_publication or await create_publication(
            db,
            user_id=current_user.id,
            listing_id=listing.id,
            platform="amazon",
            channel_id=str(connection.id),
            idempotency_key=idempotency_key,
        )
        publication.status = "completed"
        publication.external_product_id = variant.sku
        listing.status = "published"
        listing.published_at = datetime.now(timezone.utc)
        record = MarketingCampaignPublication(
            user_id=current_user.id,
            campaign_id=campaign.id,
            copy_id=copy_asset.id,
            listing_id=listing.id,
            publication_id=publication.id,
            platform="amazon",
            channel_id=payload.channel_id,
            status="completed",
            external_product_id=variant.sku,
            error=None,
            idempotency_key=idempotency_key or None,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return _serialize_publication(record)

    if not payload.copy_id or not payload.channel_id:
        raise HTTPException(status_code=400, detail="Shopify 发布需要文案和店铺渠道")
    try:
        copy_id = uuid.UUID(payload.copy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="文案 ID 无效")
    copy_asset = await _owned_copy(
        db,
        campaign.id,
        copy_id,
        current_user.id,
    )
    if copy_asset is None:
        raise HTTPException(status_code=404, detail="文案不存在")
    if copy_asset.platform != "shopify":
        raise HTTPException(status_code=400, detail="请选择 Shopify 平台文案")
    if copy_asset.compliance_status != "pass":
        raise HTTPException(status_code=409, detail="文案未通过合规检查")
    if not campaign.product_id:
        raise HTTPException(status_code=409, detail="活动尚未绑定商品")
    product = await db.get(Product, campaign.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="活动商品不存在")
    try:
        channel_uuid = uuid.UUID(payload.channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Shopify 渠道 ID 无效")
    channel = (
        await db.execute(
            select(ShopifyChannel).where(
                ShopifyChannel.id == channel_uuid,
                ShopifyChannel.user_id == current_user.id,
                ShopifyChannel.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Shopify 店铺不存在或未启用")

    try:
        violations = json.loads(copy_asset.violations_json or "[]")
    except (json.JSONDecodeError, TypeError):
        violations = []
    listing = await persist_generated_listing(
        db,
        user=current_user,
        product=product,
        platform="shopify",
        language=copy_asset.language,
        tone="marketing",
        title=copy_asset.headline,
        description=copy_asset.body,
        bullet_points=[copy_asset.cta],
        seo_title=copy_asset.headline[:200],
        seo_description=copy_asset.body[:160],
        violations=violations if isinstance(violations, list) else [],
        blocked=False,
        ai_model_used=copy_asset.model_used or "marketing-copy",
    )
    try:
        variant_ids = [uuid.UUID(value) for value in payload.variant_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="SKU 变体 ID 无效")
    try:
        result = await publish_shopify_product(
            db,
            user=current_user,
            product=product,
            listing=listing,
            channel=channel,
            idempotency_key=idempotency_key,
            variant_ids=variant_ids or None,
        )
    except ShopifyPublishError as exc:
        record = MarketingCampaignPublication(
            user_id=current_user.id,
            campaign_id=campaign.id,
            copy_id=copy_asset.id,
            listing_id=listing.id,
            platform="shopify",
            channel_id=payload.channel_id,
            status="failed",
            error=str(exc),
            idempotency_key=idempotency_key or None,
        )
        db.add(record)
        await db.commit()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    publication = result.publication
    record = MarketingCampaignPublication(
        user_id=current_user.id,
        campaign_id=campaign.id,
        copy_id=copy_asset.id,
        listing_id=listing.id,
        publication_id=publication.id,
        platform="shopify",
        channel_id=payload.channel_id,
        status=publication.status,
        external_product_id=publication.external_product_id,
        external_url=publication.external_url,
        error=publication.error,
        idempotency_key=idempotency_key or None,
    )
    db.add(record)
    await db.commit()
    return _serialize_publication(record)


@router.post("/{campaign_id}/metrics", status_code=201)
async def import_campaign_metrics(
    campaign_id: str,
    payload: PerformanceImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    items = []
    for value in payload.items:
        if value.period_end < value.period_start:
            raise HTTPException(status_code=400, detail="效果数据时间范围无效")
        existing = (
            await db.execute(
                select(MarketingPerformanceSnapshot).where(
                    MarketingPerformanceSnapshot.user_id == current_user.id,
                    MarketingPerformanceSnapshot.campaign_id == campaign.id,
                    MarketingPerformanceSnapshot.platform == value.platform,
                    MarketingPerformanceSnapshot.source == value.source,
                    MarketingPerformanceSnapshot.period_start == value.period_start,
                    MarketingPerformanceSnapshot.period_end == value.period_end,
                    MarketingPerformanceSnapshot.scope_key
                    == (value.copy_id or ""),
                )
            )
        ).scalar_one_or_none()
        copy_asset = await _resolve_metric_copy(
            db,
            campaign.id,
            value.copy_id,
            current_user.id,
        )
        snapshot = existing or MarketingPerformanceSnapshot(
            user_id=current_user.id,
            campaign_id=campaign.id,
            platform=value.platform,
            source=value.source,
            copy_id=copy_asset.id if copy_asset else None,
            scope_key=str(copy_asset.id) if copy_asset else "",
            period_start=value.period_start,
            period_end=value.period_end,
        )
        snapshot.copy_id = copy_asset.id if copy_asset else None
        snapshot.scope_key = str(copy_asset.id) if copy_asset else ""
        snapshot.impressions = value.impressions
        snapshot.clicks = value.clicks
        snapshot.orders = value.orders
        snapshot.conversions = value.conversions
        snapshot.spend = value.spend
        snapshot.revenue = value.revenue
        snapshot.currency = value.currency.upper()
        snapshot.metadata_json = json.dumps(value.metadata, ensure_ascii=False)
        db.add(snapshot)
        items.append(snapshot)
    await db.flush()
    if await automation_enabled_for_user(db, current_user, "ab_evaluation"):
        await evaluate_campaign_ab_performance(
            db,
            campaign_id=campaign.id,
            user_id=current_user.id,
        )
        await record_task_state(
            db,
            user_id=current_user.id,
            task="ab_evaluation",
            status="success",
        )
    for item in items:
        await db.refresh(item)
    return {
        "total": len(items),
        "items": [_serialize_snapshot(item) for item in items],
    }


@router.post("/{campaign_id}/metrics/import", status_code=201)
async def import_campaign_metrics_csv(
    campaign_id: str,
    payload: AdMetricCsvImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导入 Amazon Ads、TikTok Ads 或 Meta Ads 官方导出 CSV。"""
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=400, detail="效果数据时间范围无效")
    copy_asset = await _resolve_metric_copy(
        db,
        campaign.id,
        payload.copy_id,
        current_user.id,
    )
    try:
        metrics = parse_ad_metrics_csv(payload.provider, payload.csv_text)
    except AdsMetricImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scope_key = str(copy_asset.id) if copy_asset else ""
    snapshot = (
        await db.execute(
            select(MarketingPerformanceSnapshot).where(
                MarketingPerformanceSnapshot.user_id == current_user.id,
                MarketingPerformanceSnapshot.campaign_id == campaign.id,
                MarketingPerformanceSnapshot.platform == metrics.platform,
                MarketingPerformanceSnapshot.source == metrics.source,
                MarketingPerformanceSnapshot.period_start == payload.period_start,
                MarketingPerformanceSnapshot.period_end == payload.period_end,
                MarketingPerformanceSnapshot.scope_key == scope_key,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = MarketingPerformanceSnapshot(
            user_id=current_user.id,
            campaign_id=campaign.id,
            platform=metrics.platform,
            source=metrics.source,
            copy_id=copy_asset.id if copy_asset else None,
            scope_key=scope_key,
            period_start=payload.period_start,
            period_end=payload.period_end,
        )
    snapshot.copy_id = copy_asset.id if copy_asset else None
    snapshot.scope_key = scope_key
    snapshot.impressions = metrics.impressions
    snapshot.clicks = metrics.clicks
    snapshot.orders = metrics.orders
    snapshot.conversions = metrics.conversions
    snapshot.spend = metrics.spend
    snapshot.revenue = metrics.revenue
    snapshot.currency = metrics.currency
    snapshot.metadata_json = json.dumps(
        {
            "provider": metrics.provider,
            "import_format": "csv",
            "variant_key": copy_asset.variant_key if copy_asset else None,
        },
        ensure_ascii=False,
    )
    db.add(snapshot)
    await db.flush()
    if await automation_enabled_for_user(db, current_user, "ab_evaluation"):
        await evaluate_campaign_ab_performance(
            db,
            campaign_id=campaign.id,
            user_id=current_user.id,
        )
        await record_task_state(
            db,
            user_id=current_user.id,
            task="ab_evaluation",
            status="success",
        )
    await db.commit()
    await db.refresh(snapshot)
    return {
        "provider": metrics.provider,
        "item": _serialize_snapshot(snapshot),
    }


@router.get("/{campaign_id}/performance")
async def get_campaign_performance(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    snapshots = (
        await db.execute(
            select(MarketingPerformanceSnapshot)
            .where(
                MarketingPerformanceSnapshot.user_id == current_user.id,
                MarketingPerformanceSnapshot.campaign_id == campaign.id,
            )
            .order_by(desc(MarketingPerformanceSnapshot.period_end))
            .limit(365)
        )
    ).scalars().all()
    totals = _aggregate_performance(snapshots)
    return {
        "totals": totals,
        "currency": next(
            (item.currency for item in snapshots if item.currency),
            "USD",
        ),
        "items": [_serialize_snapshot(item) for item in snapshots],
    }


@router.get("/{campaign_id}/optimization")
async def get_campaign_optimization(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """根据活动汇总数据生成不编造事实的优化建议。"""
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    snapshots = (
        await db.execute(
            select(MarketingPerformanceSnapshot).where(
                MarketingPerformanceSnapshot.user_id == current_user.id,
                MarketingPerformanceSnapshot.campaign_id == campaign.id,
            )
        )
    ).scalars().all()
    copies = (
        await db.execute(
            select(MarketingCopyAsset).where(
                MarketingCopyAsset.user_id == current_user.id,
                MarketingCopyAsset.campaign_id == campaign.id,
            )
        )
    ).scalars().all()
    totals = _aggregate_performance(list(snapshots))
    ab_auto_pause = await automation_enabled_for_user(
        db,
        current_user,
        "ab_evaluation",
    )
    variant_analysis = evaluate_variant_performance(
        list(copies),
        list(snapshots),
        persist=ab_auto_pause,
    )
    asset_actions = build_optimization_asset_actions(variant_analysis)
    recommendations: list[dict] = []
    if not snapshots:
        recommendations.append({
            "code": "collect_performance",
            "severity": "info",
            "title": "先积累效果数据",
            "detail": "当前活动还没有曝光、点击或订单数据。",
            "action": "同步 Shopify 订单，或导入广告平台效果快照。",
        })
    else:
        if totals["impressions"] and totals["ctr"] < 1:
            recommendations.append({
                "code": "improve_hook",
                "severity": "warning",
                "title": "优先优化前 3 秒钩子",
                "detail": f"当前 CTR 为 {totals['ctr']}%，低于 1% 的冷启动参考线。",
                "action": "测试更直接的利益点、问题场景或强对比封面。",
            })
        if totals["clicks"] and totals["cvr"] < 2:
            recommendations.append({
                "code": "improve_conversion",
                "severity": "warning",
                "title": "检查点击后的转化承接",
                "detail": f"当前 CVR 为 {totals['cvr']}%，点击后下单率偏低。",
                "action": "检查商品页价格、折扣、配送承诺与文案是否一致。",
            })
        if totals["spend"] and totals["roas"] < 1.5:
            recommendations.append({
                "code": "reduce_spend",
                "severity": "danger",
                "title": "收紧低回报投放",
                "detail": f"当前 ROAS 为 {totals['roas']}，低于 1.5 的止损参考线。",
                "action": "暂停低转化素材并缩小受众，不要直接扩大预算。",
            })
        elif totals["roas"] >= 3:
            recommendations.append({
                "code": "scale_winner",
                "severity": "success",
                "title": "放大高回报组合",
                "detail": f"当前 ROAS 为 {totals['roas']}，具备继续放量基础。",
                "action": "逐步提高预算，并复用当前高表现素材和文案结构。",
            })
    blocked_copies = [item for item in copies if item.compliance_status == "block"]
    if blocked_copies:
        recommendations.append({
            "code": "fix_compliance",
            "severity": "danger",
            "title": "先修复未通过合规的文案",
            "detail": f"当前有 {len(blocked_copies)} 条文案存在合规问题。",
            "action": "前往文案素材板修改后重新执行合规检查。",
        })
    if not any(item.copy_id for item in snapshots):
        recommendations.append({
            "code": "connect_variant_metrics",
            "severity": "info",
            "title": "补齐 A/B 版本级数据",
            "detail": "当前效果快照没有绑定具体 A/B 文案，不能据此宣布任一变体获胜。",
            "action": "后续广告数据导入时携带 copy_id，再判断暂停或放量版本。",
        })
    if any(
        item["performance_status"] == "paused"
        for item in variant_analysis
    ):
        recommendations.append({
            "code": "ab_loser_paused",
            "severity": "warning",
            "title": "已暂停明显落后的 A/B 版本",
            "detail": "系统仅在样本充足且差距明确时自动暂停。",
            "action": "保留赢家继续投放，并参考素材动作重做落后版本。",
        })
    if any(
        item["performance_status"] == "winner"
        for item in variant_analysis
    ):
        recommendations.append({
            "code": "ab_winner_recommended",
            "severity": "success",
            "title": "已有可继续放大的 A/B 版本",
            "detail": "赢家版本的相对表现已达到自动判断门槛。",
            "action": "逐步增加预算，同时保留对照版本观察衰减。",
        })
    return {
        "metrics": totals,
        "variant_analysis": variant_analysis,
        "asset_actions": asset_actions,
        "recommendations": recommendations,
    }
