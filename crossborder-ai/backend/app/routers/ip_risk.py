"""IP 风险初筛 API。"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.image_asset import ImageAsset
from app.models.ip_risk import IpDeclaration
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.user import User
from app.services.ip_risk import (
    get_owned_ip_report,
    screen_product_text,
)


router = APIRouter(prefix="/ip-risk", tags=["IP Risk"])


class IpRiskScreenRequest(BaseModel):
    product_id: uuid.UUID
    listing_id: uuid.UUID | None = None
    image_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    scope: Literal["text", "image", "both"] = "text"
    trigger: Literal["generation", "manual", "agent", "publish"] = "manual"
    category_code: str | None = None
    text_fields: dict[str, str] | None = None


class IpDeclarationRequest(BaseModel):
    product_id: uuid.UUID
    claim_type: Literal["brand_authorization", "certification"]
    claim_value: str
    evidence_url: str | None = None
    evidence_status: Literal[
        "provided",
        "manually_verified",
        "unverified",
        "expired",
    ] = "provided"
    expires_at: datetime | None = None


@router.post("/screen", status_code=201)
async def screen_ip_risk(
    payload: IpRiskScreenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行用户拥有的商品/Listing IP 初筛并保存报告。"""
    product = await db.get(Product, payload.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="商品不存在")

    listing = None
    if payload.listing_id:
        listing = await db.get(ListingDraft, payload.listing_id)
        if (
            listing is None
            or listing.user_id != current_user.id
            or listing.product_id != product.id
        ):
            raise HTTPException(status_code=404, detail="Listing 不存在")

    image_assets = []
    if payload.image_asset_ids:
        image_assets = (
            await db.execute(
                select(ImageAsset).where(
                    ImageAsset.user_id == current_user.id,
                    ImageAsset.id.in_(payload.image_asset_ids),
                )
            )
        ).scalars().all()
        if len({asset.id for asset in image_assets}) != len(set(payload.image_asset_ids)):
            raise HTTPException(status_code=404, detail="部分图片素材不存在")

    return await screen_product_text(
        db,
        user=current_user,
        product=product,
        listing=listing,
        platform=listing.platform if listing else "amazon",
        category_code=payload.category_code,
        trigger=payload.trigger,
        scope=payload.scope,
        text_fields=payload.text_fields,
        image_assets=list(image_assets),
    )


@router.get("/reports/{report_id}")
async def get_ip_risk_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await get_owned_ip_report(
        db,
        user_id=current_user.id,
        report_id=report_id,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="IP 风险报告不存在")
    return report


@router.get("/declarations")
async def list_ip_declarations(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="商品不存在")
    rows = (
        await db.execute(
            select(IpDeclaration).where(
                IpDeclaration.user_id == current_user.id,
                IpDeclaration.product_id == product.id,
            )
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(row.id),
                "claim_type": row.claim_type,
                "claim_value": row.claim_value,
                "evidence_url": row.evidence_url,
                "evidence_status": row.evidence_status,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in rows
        ]
    }


@router.post("/declarations", status_code=201)
async def save_ip_declaration(
    payload: IpDeclarationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, payload.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="商品不存在")
    claim_value = payload.claim_value.strip()
    if not claim_value:
        raise HTTPException(status_code=400, detail="授权或认证名称不能为空")
    row = (
        await db.execute(
            select(IpDeclaration).where(
                IpDeclaration.product_id == product.id,
                IpDeclaration.claim_type == payload.claim_type,
                IpDeclaration.claim_value == claim_value,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = IpDeclaration(
            user_id=current_user.id,
            product_id=product.id,
            claim_type=payload.claim_type,
            claim_value=claim_value,
        )
        db.add(row)
    row.evidence_url = payload.evidence_url
    row.evidence_status = payload.evidence_status
    row.expires_at = payload.expires_at
    await db.flush()
    await db.refresh(row)
    return {
        "id": str(row.id),
        "claim_type": row.claim_type,
        "claim_value": row.claim_value,
        "evidence_url": row.evidence_url,
        "evidence_status": row.evidence_status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


@router.delete("/declarations/{declaration_id}", status_code=204)
async def delete_ip_declaration(
    declaration_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(IpDeclaration, declaration_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="授权声明不存在")
    await db.delete(row)
    await db.flush()
    return None
