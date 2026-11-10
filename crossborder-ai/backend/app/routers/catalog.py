"""跨商品 SKU、变体与 Listing 中心。"""

import itertools
import json
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.routers.product_variants import _serialize_variant
from app.services.platform_rules import (
    list_platform_rules,
    validate_listing_for_platform,
)


router = APIRouter(prefix="/catalog", tags=["Catalog Center"])


class CatalogVariantListResponse(BaseModel):
    items: list[dict]
    total: int


class VariantMatrixRequest(BaseModel):
    attribute_groups: dict[str, list[str]] = Field(..., min_length=1)
    sku_prefix: str = Field(..., min_length=1, max_length=30)
    price: Optional[float] = Field(None, ge=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(0, ge=0)
    is_active: bool = True


class BulkVariantUpdateRequest(BaseModel):
    variant_ids: list[UUID] = Field(..., min_length=1, max_length=500)
    price: Optional[float] = Field(None, ge=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    image_url: Optional[str] = Field(None, max_length=1000)


def _parse_attributes(raw: Optional[str]) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_bullets(raw: Optional[str]) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _canonical_attributes(attributes: dict[str, str]) -> str:
    return json.dumps(attributes, ensure_ascii=False, sort_keys=True)


def _normalize_sku_prefix(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip().upper()).strip("-_")
    return normalized[:30] or "SKU"


def _serialize_catalog_variant(variant: ProductVariant, product_title: str) -> dict:
    return {
        **_serialize_variant(variant),
        "product_title": product_title,
    }


@router.get("/variants", response_model=CatalogVariantListResponse)
async def list_catalog_variants(
    search: Optional[str] = Query(None, max_length=100),
    product_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    low_stock: bool = False,
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跨商品查询当前用户 SKU。"""
    query = (
        select(ProductVariant, Product.title)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.user_id == current_user.id)
    )
    if search:
        keyword = f"%{search.strip()}%"
        query = query.where(
            or_(
                ProductVariant.sku.ilike(keyword),
                ProductVariant.name.ilike(keyword),
                Product.title.ilike(keyword),
            )
        )
    if product_id:
        try:
            query = query.where(ProductVariant.product_id == UUID(product_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的商品 ID")
    if is_active is not None:
        query = query.where(ProductVariant.is_active == is_active)
    if low_stock:
        query = query.where(ProductVariant.stock_quantity < 10)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0
    result = await db.execute(
        query.order_by(desc(ProductVariant.updated_at)).limit(limit)
    )
    return CatalogVariantListResponse(
        items=[
            _serialize_catalog_variant(variant, product_title)
            for variant, product_title in result.all()
        ],
        total=total,
    )


@router.post(
    "/products/{product_id}/variants/generate",
    status_code=status.HTTP_201_CREATED,
)
async def generate_variant_matrix(
    product_id: str,
    payload: VariantMatrixRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按属性笛卡尔组合生成缺失 SKU，重复执行保持幂等。"""
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的商品 ID")
    product = (
        await db.execute(
            select(Product).where(
                Product.id == pid,
                Product.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    cleaned_groups: list[tuple[str, list[str]]] = []
    for key, values in payload.attribute_groups.items():
        clean_key = key.strip()
        clean_values = list(dict.fromkeys(
            value.strip() for value in values if value and value.strip()
        ))
        if clean_key and clean_values:
            cleaned_groups.append((clean_key, clean_values))
    if not cleaned_groups:
        raise HTTPException(status_code=400, detail="至少填写一个有效属性和属性值")

    combinations = list(itertools.product(*(values for _, values in cleaned_groups)))
    if len(combinations) > 100:
        raise HTTPException(status_code=400, detail="单次最多生成 100 个变体组合")

    existing = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.user_id == current_user.id,
                ProductVariant.product_id == product.id,
            )
        )
    ).scalars().all()
    existing_attributes = {
        _canonical_attributes(_parse_attributes(item.attributes_json))
        for item in existing
    }
    used_skus = {
        row.sku
        for row in (
            await db.execute(
                select(ProductVariant).where(ProductVariant.user_id == current_user.id)
            )
        ).scalars().all()
    }

    prefix = _normalize_sku_prefix(payload.sku_prefix)
    next_index = 1
    created_items: list[ProductVariant] = []
    skipped = 0
    for combination in combinations:
        attributes = {
            key: value
            for (key, _), value in zip(cleaned_groups, combination)
        }
        canonical = _canonical_attributes(attributes)
        if canonical in existing_attributes:
            skipped += 1
            continue

        candidate = f"{prefix}-{next_index:02d}"
        while candidate in used_skus:
            next_index += 1
            candidate = f"{prefix}-{next_index:02d}"
        next_index += 1
        variant = ProductVariant(
            user_id=current_user.id,
            product_id=product.id,
            sku=candidate,
            name=" / ".join(combination),
            attributes_json=json.dumps(attributes, ensure_ascii=False),
            price=payload.price,
            cost_price=payload.cost_price,
            stock_quantity=payload.stock_quantity,
            is_active=payload.is_active,
        )
        db.add(variant)
        created_items.append(variant)
        used_skus.add(candidate)
        existing_attributes.add(canonical)

    await db.flush()
    for variant in created_items:
        await db.refresh(variant)
    return {
        "items": [
            _serialize_catalog_variant(variant, product.title or "")
            for variant in created_items
        ],
        "created": len(created_items),
        "skipped": skipped,
    }


@router.patch("/variants/bulk")
async def bulk_update_variants(
    payload: BulkVariantUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """原子批量修改本人 SKU，混入他人变体时整批回滚。"""
    if len(set(payload.variant_ids)) != len(payload.variant_ids):
        raise HTTPException(status_code=422, detail="批量请求不能包含重复变体")
    result = await db.execute(
        select(ProductVariant, Product.title)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.id.in_(payload.variant_ids),
            ProductVariant.user_id == current_user.id,
        )
    )
    rows = result.all()
    if len(rows) != len(payload.variant_ids):
        raise HTTPException(status_code=404, detail="一个或多个变体不存在")

    fields = payload.model_fields_set
    if not fields - {"variant_ids"}:
        raise HTTPException(status_code=400, detail="至少提交一个需要修改的字段")
    for variant, _ in rows:
        if "price" in fields:
            variant.price = payload.price
        if "cost_price" in fields:
            variant.cost_price = payload.cost_price
        if "stock_quantity" in fields:
            variant.stock_quantity = payload.stock_quantity
        if "is_active" in fields:
            variant.is_active = payload.is_active
        if "image_url" in fields:
            variant.image_url = payload.image_url

    await db.flush()
    for variant, _ in rows:
        await db.refresh(variant)
    return {
        "items": [
            _serialize_catalog_variant(variant, product_title)
            for variant, product_title in rows
        ],
        "updated": len(rows),
    }


@router.get("/listings")
async def list_catalog_listings(
    platform: Optional[str] = None,
    listing_status: Optional[str] = Query(None, alias="status"),
    compliance_status: Optional[str] = None,
    search: Optional[str] = Query(None, max_length=100),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跨商品查询 Listing 并附带平台字段就绪结果。"""
    query = (
        select(ListingDraft, Product.title)
        .join(Product, Product.id == ListingDraft.product_id)
        .where(ListingDraft.user_id == current_user.id)
    )
    if platform:
        query = query.where(ListingDraft.platform == platform)
    if listing_status:
        query = query.where(ListingDraft.status == listing_status)
    if compliance_status:
        query = query.where(ListingDraft.compliance_status == compliance_status)
    if search:
        keyword = f"%{search.strip()}%"
        query = query.where(
            or_(
                ListingDraft.title.ilike(keyword),
                Product.title.ilike(keyword),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0
    result = await db.execute(
        query.order_by(desc(ListingDraft.updated_at)).limit(limit)
    )
    items = []
    for listing, product_title in result.all():
        bullets = _parse_bullets(listing.bullet_points)
        readiness = validate_listing_for_platform(
            listing.platform,
            {
                "title": listing.title,
                "description": listing.description,
                "bullet_points": bullets,
                "seo_title": listing.seo_title,
                "seo_description": listing.seo_description,
            },
        )
        items.append(
            {
                "id": str(listing.id),
                "product_id": str(listing.product_id),
                "product_title": product_title,
                "platform": listing.platform,
                "language": listing.language,
                "title": listing.title,
                "status": listing.status,
                "compliance_status": listing.compliance_status,
                "version": listing.version,
                "bullet_count": len(bullets),
                "readiness": readiness,
                "created_at": str(listing.created_at),
                "updated_at": str(listing.updated_at),
            }
        )
    return {"items": items, "total": total}


@router.get("/platform-rules")
async def get_catalog_platform_rules(
    current_user: User = Depends(get_current_user),
):
    return {"items": list_platform_rules()}
