"""VOC 评论导入与洞察接口。"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.product import Product
from app.models.user import User
from app.models.voc import VocAnalysis
from app.services.voc_service import (
    analyze_reviews,
    parse_review_input,
    serialize_voc,
)


router = APIRouter(prefix="/voc", tags=["VOC"])


class VocAnalyzeRequest(BaseModel):
    product_id: str | None = None
    platform: str = Field("amazon", max_length=50)
    language: str = Field("en", max_length=20)
    reviews: str = Field(..., min_length=1, max_length=200_000)


@router.post("/analyze")
async def analyze_voc(
    payload: VocAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    reviews = parse_review_input(payload.reviews)
    if not reviews:
        raise HTTPException(status_code=400, detail="没有可分析的评论")
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="积分不足，VOC 分析需要 1 积分")

    product = None
    product_id = None
    if payload.product_id:
        try:
            product_id = uuid.UUID(payload.product_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的商品 ID")
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

    result, model_used = await analyze_reviews(
        reviews,
        product_title=product.title if product else "Unknown product",
        platform=payload.platform,
        language=payload.language,
    )
    analysis = VocAnalysis(
        user_id=current_user.id,
        product_id=product_id,
        platform=payload.platform,
        language=payload.language,
        review_count=len(reviews),
        summary=result["summary"],
        pain_points_json=json.dumps(result["pain_points"], ensure_ascii=False),
        selling_points_json=json.dumps(result["selling_points"], ensure_ascii=False),
        objections_json=json.dumps(result["objections"], ensure_ascii=False),
        keywords_json=json.dumps(result["keywords"], ensure_ascii=False),
        sentiment_json=json.dumps(result["sentiment"], ensure_ascii=False),
        recommendations_json=json.dumps(result["recommendations"], ensure_ascii=False),
        model_used=model_used,
    )
    db.add(analysis)
    await db.flush()
    await current_user.deduct_credits(
        db,
        1,
        feature="voc_analysis",
        reference_type="voc_analysis",
        reference_id=str(analysis.id),
        description="VOC 评论洞察",
    )
    return serialize_voc(analysis)


@router.get("/analyses")
async def list_voc_analyses(
    product_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(VocAnalysis).where(VocAnalysis.user_id == current_user.id)
    if product_id:
        try:
            query = query.where(VocAnalysis.product_id == uuid.UUID(product_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的商品 ID")
    analyses = (
        await db.execute(
            query.order_by(desc(VocAnalysis.created_at)).limit(limit)
        )
    ).scalars().all()
    return {"items": [serialize_voc(item) for item in analyses]}


@router.get("/analyses/{analysis_id}")
async def get_voc_analysis(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        aid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的 VOC 分析 ID")
    analysis = (
        await db.execute(
            select(VocAnalysis).where(
                VocAnalysis.id == aid,
                VocAnalysis.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="VOC 分析不存在")
    return serialize_voc(analysis)
