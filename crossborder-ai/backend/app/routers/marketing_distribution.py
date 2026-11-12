"""营销活动平台发布与效果数据回流。"""

import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import (
    MarketingCampaignPublication,
    MarketingPerformanceSnapshot,
)
from app.models.product import Product
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.routers.marketing_campaigns import get_owned_campaign
from app.services.listing_service import persist_generated_listing
from app.services.shopify_publish_service import (
    ShopifyPublishError,
    publish_shopify_product,
)


router = APIRouter(prefix="/marketing-campaigns", tags=["营销 Agent"])

SUPPORTED_PUBLISH_PLATFORMS = {"shopify", "amazon"}


class CampaignPublicationRequest(BaseModel):
    platform: str
    copy_id: Optional[str] = None
    channel_id: Optional[str] = None
    variant_ids: list[str] = Field(default_factory=list)


class PerformanceSnapshotInput(BaseModel):
    platform: str
    source: str = "manual"
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
        record = MarketingCampaignPublication(
            user_id=current_user.id,
            campaign_id=campaign.id,
            platform="amazon",
            status="unavailable",
            error="Amazon SP-API 已支持授权连接，但 Listing 发布接口尚未接入",
            idempotency_key=idempotency_key or None,
        )
        db.add(record)
        await db.flush()
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
                )
            )
        ).scalar_one_or_none()
        snapshot = existing or MarketingPerformanceSnapshot(
            user_id=current_user.id,
            campaign_id=campaign.id,
            platform=value.platform,
            source=value.source,
            period_start=value.period_start,
            period_end=value.period_end,
        )
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
    for item in items:
        await db.refresh(item)
    return {
        "total": len(items),
        "items": [_serialize_snapshot(item) for item in items],
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
    return {
        "totals": totals,
        "currency": next(
            (item.currency for item in snapshots if item.currency),
            "USD",
        ),
        "items": [_serialize_snapshot(item) for item in snapshots],
    }
