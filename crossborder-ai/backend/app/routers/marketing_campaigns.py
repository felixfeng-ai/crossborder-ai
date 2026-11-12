"""营销活动 API。"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.image_asset import ImageAsset
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_video import MarketingVideoProject
from app.models.product import Product
from app.models.user import User
from app.models.image_generation_task import ImageGenerationTask
from app.models.video_generation_task import VideoGenerationTask


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


@router.get("/{campaign_id}/assets")
async def list_campaign_assets(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按活动聚合素材；活动归属和素材用户范围必须同时校验。"""
    campaign = await get_owned_campaign(
        db,
        current_user.id,
        campaign_id,
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="营销活动不存在")

    image_tasks = (
        await db.execute(
            select(ImageGenerationTask)
            .where(
                ImageGenerationTask.user_id == current_user.id,
                ImageGenerationTask.campaign_id == campaign.id,
            )
            .order_by(desc(ImageGenerationTask.created_at))
            .limit(50)
        )
    ).scalars().all()
    generated_assets = (
        await db.execute(
            select(ImageAsset)
            .where(
                ImageAsset.user_id == current_user.id,
                ImageAsset.kind == "generated",
                ImageAsset.generation_task_id.in_(
                    [task.id for task in image_tasks]
                ),
            )
            .order_by(ImageAsset.variant_index)
        )
    ).scalars().all() if image_tasks else []
    generated_by_task: dict = {}
    for asset in generated_assets:
        if asset.generation_task_id is not None:
            generated_by_task.setdefault(asset.generation_task_id, asset)
    video_tasks = (
        await db.execute(
            select(VideoGenerationTask)
            .where(
                VideoGenerationTask.user_id == current_user.id,
                VideoGenerationTask.campaign_id == campaign.id,
            )
            .order_by(desc(VideoGenerationTask.created_at))
            .limit(30)
        )
    ).scalars().all()
    projects = (
        await db.execute(
            select(MarketingVideoProject)
            .where(
                MarketingVideoProject.user_id == current_user.id,
                MarketingVideoProject.campaign_id == campaign.id,
            )
            .order_by(desc(MarketingVideoProject.created_at))
            .limit(20)
        )
    ).scalars().all()

    items = []
    for task in image_tasks:
        try:
            urls = json.loads(task.image_urls or "[]")
        except (json.JSONDecodeError, TypeError):
            urls = []
        generated_asset = generated_by_task.get(task.id)
        thumbnail_url = (
            f"{settings.API_V1_PREFIX}/images/assets/{generated_asset.id}/file"
            if generated_asset is not None
            else urls[0] if isinstance(urls, list) and urls else None
        )
        items.append({
            "id": str(task.id),
            "kind": "image",
            "status": task.status,
            "prompt": task.prompt,
            "urls": urls if isinstance(urls, list) else [],
            "thumbnail_url": thumbnail_url,
            "image_asset_id": (
                str(generated_asset.id) if generated_asset is not None else None
            ),
            "credits": task.credits_charged or task.credits_cost,
            "created_at": str(task.created_at),
        })
    for task in video_tasks:
        has_file = task.status == "succeeded" and bool(task.storage_key)
        items.append({
            "id": str(task.id),
            "kind": "video",
            "status": task.status,
            "prompt": task.prompt,
            "urls": (
                [f"{settings.API_V1_PREFIX}/videos/tasks/{task.id}/file"]
                if has_file
                else []
            ),
            "thumbnail_url": (
                f"{settings.API_V1_PREFIX}/videos/tasks/{task.id}/thumbnail"
                if has_file
                else None
            ),
            "credits": task.credits_charged or task.credits_cost,
            "created_at": str(task.created_at),
        })
    for project in projects:
        has_file = project.status == "succeeded" and bool(project.final_storage_key)
        items.append({
            "id": str(project.id),
            "kind": "marketing_video",
            "status": project.status,
            "prompt": project.idea,
            "urls": (
                [
                    f"{settings.API_V1_PREFIX}/marketing-videos/"
                    f"projects/{project.id}/file"
                ]
                if has_file
                else []
            ),
            "thumbnail_url": (
                f"{settings.API_V1_PREFIX}/marketing-videos/"
                f"projects/{project.id}/thumbnail"
                if has_file
                else None
            ),
            "credits": project.credits_charged or project.credits_estimated,
            "created_at": str(project.created_at),
        })
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "counts": {
            "images": len(image_tasks),
            "videos": len(video_tasks),
            "marketing_videos": len(projects),
            "total": len(items),
        },
        "items": items,
    }
