"""v1 商品管理接口。

VeyaShip - Product Endpoints.

CRUD operations for user products."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, PaginationParams
from app.models.user import User
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate, ProductListResponse

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    search: Optional[str] = Query(None, description="Search by title or SKU"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all products for the current user."""
    query = select(Product).where(Product.owner_id == current_user.id)

    if search:
        query = query.where(
            or_(
                Product.title.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%"),
            )
        )
    if category:
        query = query.where(Product.category == category)
    if is_active is not None:
        query = query.where(Product.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Get paginated results
    query = query.order_by(Product.updated_at.desc())
    query = query.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(query)
    products = result.scalars().all()

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=max(1, (total + pagination.page_size - 1) // pagination.page_size),
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single product by ID."""
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.owner_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new product."""
    product = Product(
        owner_id=current_user.id,
        title=payload.title,
        description=payload.description,
        sku=payload.sku,
        barcode=payload.barcode,
        price=payload.price,
        compare_at_price=payload.compare_at_price,
        cost_price=payload.cost_price,
        stock_quantity=payload.stock_quantity,
        image_url=payload.image_url,
        additional_images=(
            ",".join(payload.additional_images) if payload.additional_images else None
        ),
        category=payload.category,
        tags=",".join(payload.tags) if payload.tags else None,
        weight=payload.weight,
        weight_unit=payload.weight_unit,
    )
    db.add(product)
    await db.flush()
    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing product."""
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.owner_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "tags" in update_data and isinstance(update_data["tags"], list):
        update_data["tags"] = ",".join(update_data["tags"])
    if "additional_images" in update_data and isinstance(update_data["additional_images"], list):
        update_data["additional_images"] = ",".join(update_data["additional_images"])

    for field, value in update_data.items():
        setattr(product, field, value)

    db.add(product)
    await db.flush()
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a product."""
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.owner_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)
    await db.flush()
