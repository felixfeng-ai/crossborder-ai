"""Listing 查看、人工编辑与重新合规接口。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.product import Product
from app.services.ai.persona_kit import build_persona_kit, fetch_persona
from app.services.listing_service import (
    get_owned_listing,
    run_listing_compliance,
    serialize_listing,
    update_listing_content,
)
from app.services.ip_risk import screen_product_text


router = APIRouter(prefix="/listings", tags=["Listings"])


class ListingUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    bullet_points: Optional[list[str]] = None
    seo_title: Optional[str] = Field(None, max_length=500)
    seo_description: Optional[str] = None


async def _owned_listing_or_404(
    db: AsyncSession,
    listing_id: str,
    current_user: User,
):
    """读取当前用户 Listing；他人或不存在统一返回 404，避免泄露资源存在性。"""
    listing = await get_owned_listing(db, listing_id, current_user.id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing 不存在")
    return listing


@router.get("/{listing_id}")
async def get_listing(
    listing_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户拥有的 Listing 详情。"""
    listing = await _owned_listing_or_404(db, listing_id, current_user)
    return serialize_listing(listing)


@router.put("/{listing_id}")
async def update_listing(
    listing_id: str,
    payload: ListingUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑 Listing 内容并自动让旧合规报告失效。"""
    listing = await _owned_listing_or_404(db, listing_id, current_user)
    if payload.title is not None and not payload.title.strip():
        raise HTTPException(status_code=400, detail="Listing 标题不能为空")

    # 版本递增和 compliance_status 重置集中在服务层完成。
    update_listing_content(
        listing,
        title=payload.title,
        description=payload.description,
        bullet_points=payload.bullet_points,
        seo_title=payload.seo_title,
        seo_description=payload.seo_description,
    )
    await db.flush()
    await db.refresh(listing)
    return serialize_listing(listing)


@router.post("/{listing_id}/compliance")
async def recheck_listing_compliance(
    listing_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重新执行当前 Listing 版本的合规检查。"""
    listing = await _owned_listing_or_404(db, listing_id, current_user)
    persona = await fetch_persona(db, current_user.id)
    persona_kit = build_persona_kit(persona) if persona else None
    await run_listing_compliance(
        db,
        listing,
        user_banned_words=(persona_kit or {}).get("banned_words") or [],
    )
    product = await db.get(Product, listing.product_id)
    ip_risk = None
    if product is not None and product.user_id == current_user.id:
        ip_risk = await screen_product_text(
            db,
            user=current_user,
            product=product,
            listing=listing,
            platform=listing.platform,
            category_code=(persona_kit or {}).get("product_category"),
            trigger="manual",
            scope="text",
        )
    await db.refresh(listing)
    return {**serialize_listing(listing), "ip_risk": ip_risk}
