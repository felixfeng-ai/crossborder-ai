"""营销活动 API。"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.marketing_campaign import MarketingCampaign
from app.models.product import Product
from app.models.user import User


router = APIRouter(prefix="/marketing-campaigns", tags=["营销 Agent"])


class CampaignCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    objective: str = Field("conversion", max_length=50)
    platform: str = Field("tiktok", max_length=50)
    market: str = Field("US", max_length=50)
    language: str = Field("en", max_length=20)
    product_id: Optional[str] = None
    budget_credits: int = Field(0, ge=0, le=10_000_000)
    brief: dict = Field(default_factory=dict)


def _serialize_campaign(campaign: MarketingCampaign) -> dict:
    try:
        brief = json.loads(campaign.brief_json or "{}")
    except (json.JSONDecodeError, TypeError):
        brief = {}
    return {
        "id": str(campaign.id),
        "product_id": str(campaign.product_id) if campaign.product_id else None,
        "title": campaign.title,
        "objective": campaign.objective,
        "platform": campaign.platform,
        "market": campaign.market,
        "language": campaign.language,
        "status": campaign.status,
        "budget_credits": campaign.budget_credits,
        "spent_credits": campaign.spent_credits,
        "brief": brief if isinstance(brief, dict) else {},
        "created_at": str(campaign.created_at),
        "updated_at": str(campaign.updated_at),
    }


async def get_owned_campaign(
    db: AsyncSession,
    user_id,
    campaign_id: str,
) -> MarketingCampaign | None:
    try:
        parsed = uuid.UUID(str(campaign_id))
    except (TypeError, ValueError):
        return None
    return (
        await db.execute(
            select(MarketingCampaign).where(
                MarketingCampaign.id == parsed,
                MarketingCampaign.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


@router.post("", status_code=201)
async def create_campaign(
    payload: CampaignCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product_id = None
    if payload.product_id:
        try:
            product_id = uuid.UUID(payload.product_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="商品 ID 无效")
        product = (
            await db.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=404, detail="商品不存在")

    campaign = MarketingCampaign(
        user_id=current_user.id,
        product_id=product_id,
        title=payload.title.strip(),
        objective=payload.objective.strip(),
        platform=payload.platform.strip(),
        market=payload.market.strip().upper(),
        language=payload.language.strip(),
        budget_credits=payload.budget_credits,
        brief_json=json.dumps(payload.brief, ensure_ascii=False),
    )
    db.add(campaign)
    await db.flush()
    return _serialize_campaign(campaign)


@router.get("")
async def list_campaigns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaigns = (
        await db.execute(
            select(MarketingCampaign)
            .where(MarketingCampaign.user_id == current_user.id)
            .order_by(
                desc(MarketingCampaign.updated_at),
                desc(MarketingCampaign.id),
            )
            .limit(50)
        )
    ).scalars().all()
    return {"items": [_serialize_campaign(item) for item in campaigns]}


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await get_owned_campaign(
        db,
        current_user.id,
        campaign_id,
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")
    return _serialize_campaign(campaign)
