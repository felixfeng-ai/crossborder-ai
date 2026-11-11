"""商品 SKU 变体 CRUD 接口。"""

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User


router = APIRouter(prefix="/products", tags=["Product Variants"])


class VariantCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    attributes: dict[str, str] = Field(default_factory=dict)
    price: Optional[float] = Field(None, ge=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(0, ge=0)
    barcode: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=1000)
    is_active: bool = True


class VariantUpdateRequest(BaseModel):
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    attributes: Optional[dict[str, str]] = None
    price: Optional[float] = Field(None, ge=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None


class VariantStockItem(BaseModel):
    """单个变体的目标库存。"""

    variant_id: UUID
    stock_quantity: int = Field(..., ge=0)


class VariantBatchStockRequest(BaseModel):
    """一次提交多个变体的库存，限制批量规模避免异常大请求。"""

    items: list[VariantStockItem] = Field(..., min_length=1, max_length=500)


def _serialize_variant(variant: ProductVariant) -> dict:
    try:
        attributes = json.loads(variant.attributes_json or "{}")
    except (json.JSONDecodeError, TypeError):
        attributes = {}
    return {
        "id": str(variant.id),
        "product_id": str(variant.product_id),
        "sku": variant.sku,
        "name": variant.name,
        "attributes": attributes,
        "price": variant.price,
        "cost_price": variant.cost_price,
        "stock_quantity": variant.stock_quantity,
        "daily_sales_rate": variant.daily_sales_rate,
        "barcode": variant.barcode,
        "image_url": variant.image_url,
        "is_active": variant.is_active,
        "created_at": str(variant.created_at),
        "updated_at": str(variant.updated_at),
    }


async def _owned_product(
    db: AsyncSession,
    product_id: str,
    user_id: UUID,
) -> Product:
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的商品 ID")
    product = (
        await db.execute(
            select(Product).where(
                Product.id == pid,
                Product.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


@router.get("/{product_id}/variants")
async def list_variants(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前用户商品的全部 SKU 变体。"""
    product = await _owned_product(db, product_id, current_user.id)
    result = await db.execute(
        select(ProductVariant)
        .where(
            ProductVariant.product_id == product.id,
            ProductVariant.user_id == current_user.id,
        )
        .order_by(ProductVariant.created_at)
    )
    variants = result.scalars().all()
    return {
        "items": [_serialize_variant(item) for item in variants],
        "total": len(variants),
    }


@router.post("/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def create_variant(
    product_id: str,
    payload: VariantCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建商品 SKU 变体，SKU 在当前用户范围内唯一。"""
    product = await _owned_product(db, product_id, current_user.id)
    exists = (
        await db.execute(
            select(ProductVariant.id).where(
                ProductVariant.user_id == current_user.id,
                ProductVariant.sku == payload.sku,
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="该 SKU 已存在")

    variant = ProductVariant(
        user_id=current_user.id,
        product_id=product.id,
        sku=payload.sku.strip(),
        name=payload.name,
        attributes_json=json.dumps(payload.attributes, ensure_ascii=False),
        price=payload.price,
        cost_price=payload.cost_price,
        stock_quantity=payload.stock_quantity,
        barcode=payload.barcode,
        image_url=payload.image_url,
        is_active=payload.is_active,
    )
    db.add(variant)
    await db.flush()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.put("/{product_id}/variants/{variant_id}")
async def update_variant(
    product_id: str,
    variant_id: str,
    payload: VariantUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新变体价格、库存、属性和启用状态。"""
    product = await _owned_product(db, product_id, current_user.id)
    try:
        vid = UUID(variant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的变体 ID")
    variant = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.id == vid,
                ProductVariant.product_id == product.id,
                ProductVariant.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if variant is None:
        raise HTTPException(status_code=404, detail="变体不存在")

    if payload.sku is not None and payload.sku != variant.sku:
        duplicate = (
            await db.execute(
                select(ProductVariant.id).where(
                    ProductVariant.user_id == current_user.id,
                    ProductVariant.sku == payload.sku,
                    ProductVariant.id != variant.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="该 SKU 已存在")
        variant.sku = payload.sku.strip()
    if payload.name is not None:
        variant.name = payload.name
    if payload.attributes is not None:
        variant.attributes_json = json.dumps(payload.attributes, ensure_ascii=False)
    if payload.price is not None:
        variant.price = payload.price
    if payload.cost_price is not None:
        variant.cost_price = payload.cost_price
    if payload.stock_quantity is not None:
        variant.stock_quantity = payload.stock_quantity
    if payload.barcode is not None:
        variant.barcode = payload.barcode
    if payload.image_url is not None:
        variant.image_url = payload.image_url
    if payload.is_active is not None:
        variant.is_active = payload.is_active

    await db.flush()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.delete("/{product_id}/variants/{variant_id}")
async def delete_variant(
    product_id: str,
    variant_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除当前用户商品下的变体。"""
    product = await _owned_product(db, product_id, current_user.id)
    try:
        vid = UUID(variant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的变体 ID")
    variant = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.id == vid,
                ProductVariant.product_id == product.id,
                ProductVariant.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if variant is None:
        raise HTTPException(status_code=404, detail="变体不存在")
    await db.delete(variant)
    await db.flush()
    return {"ok": True}


@router.patch("/{product_id}/variants/batch-stock")
async def batch_update_variant_stock(
    product_id: str,
    payload: VariantBatchStockRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """原子更新多个 SKU 库存。

    在执行任何写入前先校验整批变体归属，避免请求中混入其他商品或其他用户的
    SKU 时出现部分成功。重复 ID 也会直接拒绝，保证每个变体只有一个目标库存。
    """
    product = await _owned_product(db, product_id, current_user.id)
    variant_ids = [item.variant_id for item in payload.items]
    if len(set(variant_ids)) != len(variant_ids):
        raise HTTPException(status_code=422, detail="批量库存请求不能包含重复变体")

    variants = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.id.in_(variant_ids),
                ProductVariant.product_id == product.id,
                ProductVariant.user_id == current_user.id,
            )
        )
    ).scalars().all()
    variants_by_id = {variant.id: variant for variant in variants}
    if len(variants_by_id) != len(variant_ids):
        raise HTTPException(status_code=404, detail="一个或多个变体不存在")

    # 只有全部变体归属校验通过后才写入，保证批量请求具备原子语义。
    for item in payload.items:
        variants_by_id[item.variant_id].stock_quantity = item.stock_quantity

    await db.flush()
    # onupdate 会刷新 updated_at，显式 refresh 避免序列化时触发异步懒加载。
    for variant in variants:
        await db.refresh(variant)
    ordered_variants = [
        variants_by_id[item.variant_id]
        for item in payload.items
    ]
    return {
        "items": [_serialize_variant(variant) for variant in ordered_variants],
        "total": len(ordered_variants),
    }
