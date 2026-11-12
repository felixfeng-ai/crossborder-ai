"""营销活动多平台 A/B 文案资产 API。"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.marketing_copy import MarketingCopyAsset
from app.models.user import User
from app.routers.marketing_campaigns import get_owned_campaign
from app.services.marketing_copy_service import (
    MARKETING_COPY_PLATFORMS,
    evaluate_marketing_copy_compliance,
    generate_marketing_copy_batch,
)


router = APIRouter(prefix="/marketing-campaigns", tags=["营销 Agent"])


class GenerateMarketingCopyRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: list(MARKETING_COPY_PLATFORMS))
    language: str = Field("en", min_length=2, max_length=20)
    instructions: str = Field("", max_length=1000)


class UpdateMarketingCopyRequest(BaseModel):
    headline: Optional[str] = Field(None, min_length=1, max_length=500)
    body: Optional[str] = Field(None, min_length=1)
    cta: Optional[str] = Field(None, min_length=1, max_length=500)
    hashtags: Optional[list[str]] = None
    keywords: Optional[list[str]] = None


def _parse_list(raw: str | None) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_dict(raw: str | None) -> dict:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def serialize_marketing_copy(asset: MarketingCopyAsset) -> dict:
    return {
        "id": str(asset.id),
        "batch_id": str(asset.batch_id),
        "campaign_id": str(asset.campaign_id),
        "platform": asset.platform,
        "variant_key": asset.variant_key,
        "language": asset.language,
        "headline": asset.headline,
        "body": asset.body,
        "cta": asset.cta,
        "hashtags": _parse_list(asset.hashtags_json),
        "keywords": _parse_list(asset.keywords_json),
        "metadata": _parse_dict(asset.metadata_json),
        "status": asset.status,
        "performance_status": asset.performance_status,
        "performance_metrics": _parse_dict(asset.performance_metrics_json),
        "last_evaluated_at": (
            asset.last_evaluated_at.isoformat()
            if asset.last_evaluated_at
            else None
        ),
        "compliance_status": asset.compliance_status,
        "violations": _parse_list(asset.violations_json),
        "source": asset.source,
        "model_used": asset.model_used or "",
        "version": asset.version,
        "created_at": str(asset.created_at),
        "updated_at": str(asset.updated_at),
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


@router.get("/{campaign_id}/copy")
async def list_marketing_copy(
    campaign_id: str,
    batch_id: str | None = None,
    platform: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    query = select(MarketingCopyAsset).where(
        MarketingCopyAsset.user_id == current_user.id,
        MarketingCopyAsset.campaign_id == campaign.id,
    )
    if batch_id:
        try:
            query = query.where(MarketingCopyAsset.batch_id == uuid.UUID(batch_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="文案批次 ID 无效")
    if platform:
        query = query.where(MarketingCopyAsset.platform == platform)
    items = (
        await db.execute(
            query.order_by(
                desc(MarketingCopyAsset.created_at),
                MarketingCopyAsset.platform,
                MarketingCopyAsset.variant_key,
            ).limit(200)
        )
    ).scalars().all()
    return {
        "total": len(items),
        "items": [serialize_marketing_copy(item) for item in items],
    }


@router.post("/{campaign_id}/copy/generate", status_code=201)
async def generate_marketing_copy(
    campaign_id: str,
    payload: GenerateMarketingCopyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not check_feature_access(current_user, "agent"):
        raise HTTPException(status_code=403, detail="营销文案仅限 Standard 及以上套餐使用")
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    try:
        assets = await generate_marketing_copy_batch(
            db,
            current_user,
            campaign_id=campaign.id,
            platforms=payload.platforms,
            language=payload.language.strip(),
            instructions=payload.instructions.strip(),
            source="marketing_board",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "batch_id": str(assets[0].batch_id),
        "count": len(assets),
        "items": [serialize_marketing_copy(asset) for asset in assets],
    }


@router.patch("/{campaign_id}/copy/{copy_id}")
async def update_marketing_copy(
    campaign_id: str,
    copy_id: str,
    payload: UpdateMarketingCopyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    try:
        parsed_id = uuid.UUID(copy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="文案不存在")
    asset = await _owned_copy(db, campaign.id, parsed_id, current_user.id)
    if asset is None:
        raise HTTPException(status_code=404, detail="文案不存在")

    if payload.headline is not None:
        asset.headline = payload.headline.strip()
    if payload.body is not None:
        asset.body = payload.body.strip()
    if payload.cta is not None:
        asset.cta = payload.cta.strip()
    hashtags = _parse_list(asset.hashtags_json)
    keywords = _parse_list(asset.keywords_json)
    if payload.hashtags is not None:
        hashtags = [item.strip() for item in payload.hashtags if item.strip()][:20]
        asset.hashtags_json = json.dumps(hashtags, ensure_ascii=False)
    if payload.keywords is not None:
        keywords = [item.strip() for item in payload.keywords if item.strip()][:30]
        asset.keywords_json = json.dumps(keywords, ensure_ascii=False)
    violations = evaluate_marketing_copy_compliance(
        headline=asset.headline,
        body=asset.body,
        cta=asset.cta,
        hashtags=hashtags,
        keywords=keywords,
    )
    asset.compliance_status = "block" if violations else "pass"
    asset.violations_json = json.dumps(violations, ensure_ascii=False)
    asset.status = "blocked" if violations else "ready"
    asset.version += 1
    asset.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(asset)
    return serialize_marketing_copy(asset)


@router.post("/{campaign_id}/copy/{copy_id}/resume")
async def resume_marketing_copy(
    campaign_id: str,
    copy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """人工恢复被自动暂停的 A/B 版本，不改变文案与合规状态。"""
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    try:
        parsed_id = uuid.UUID(copy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="文案不存在")
    asset = await _owned_copy(db, campaign.id, parsed_id, current_user.id)
    if asset is None:
        raise HTTPException(status_code=404, detail="文案不存在")
    asset.performance_status = "active"
    asset.last_evaluated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(asset)
    return serialize_marketing_copy(asset)


@router.delete("/{campaign_id}/copy/{copy_id}", status_code=204)
async def delete_marketing_copy(
    campaign_id: str,
    copy_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(db, current_user.id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    try:
        parsed_id = uuid.UUID(copy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="文案不存在")
    asset = await _owned_copy(db, campaign.id, parsed_id, current_user.id)
    if asset is None:
        raise HTTPException(status_code=404, detail="文案不存在")
    await db.delete(asset)
    await db.flush()
    return None
