"""v1 Listing 查询、生成和更新接口。

VeyaShip - Listing Endpoints.

CRUD for multi-platform listings with AI generation triggers."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, PaginationParams
from app.models.user import User
from app.models.listing import Listing, ListingVariant, ListingPlatform, ListingStatus
from app.models.product import Product
from app.schemas.listing import (
    ListingCreate, ListingResponse, ListingUpdate, ListingListResponse,
)

router = APIRouter(prefix="/listings", tags=["Listings"])


@router.get("", response_model=ListingListResponse)
async def list_listings(
    platform: Optional[ListingPlatform] = Query(None, description="Filter by platform"),
    status: Optional[ListingStatus] = Query(None, description="Filter by status"),
    product_id: Optional[int] = Query(None, description="Filter by product"),
    search: Optional[str] = Query(None, description="Search by title"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all listings for the current user."""
    query = (
        select(Listing)
        .options(selectinload(Listing.variants))
        .where(Listing.owner_id == current_user.id)
    )

    if platform:
        query = query.where(Listing.platform == platform)
    if status:
        query = query.where(Listing.status == status)
    if product_id:
        query = query.where(Listing.product_id == product_id)
    if search:
        query = query.where(Listing.title.ilike(f"%{search}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(Listing.updated_at.desc())
    query = query.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    return ListingListResponse(
        items=[ListingResponse.model_validate(l) for l in listings],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=max(1, (total + pagination.page_size - 1) // pagination.page_size),
    )


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single listing by ID."""
    result = await db.execute(
        select(Listing)
        .options(selectinload(Listing.variants))
        .where(Listing.id == listing_id, Listing.owner_id == current_user.id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    payload: ListingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new listing manually."""
    # Verify product ownership if specified
    if payload.product_id:
        result = await db.execute(
            select(Product).where(
                Product.id == payload.product_id,
                Product.owner_id == current_user.id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Product not found")

    listing = Listing(
        owner_id=current_user.id,
        product_id=payload.product_id,
        platform=payload.platform,
        title=payload.title,
        description=payload.description,
        bullet_points=(
            ",".join(payload.bullet_points) if payload.bullet_points else None
        ),
        search_terms=(
            ",".join(payload.search_terms) if payload.search_terms else None
        ),
        price=payload.price,
        sale_price=payload.sale_price,
        currency=payload.currency,
        main_image_url=payload.main_image_url,
        additional_image_urls=(
            ",".join(payload.additional_image_urls)
            if payload.additional_image_urls else None
        ),
    )
    db.add(listing)
    await db.flush()
    return listing


@router.put("/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: int,
    payload: ListingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing listing."""
    result = await db.execute(
        select(Listing)
        .options(selectinload(Listing.variants))
        .where(Listing.id == listing_id, Listing.owner_id == current_user.id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    update_data = payload.model_dump(exclude_unset=True)
    # Convert list fields to comma-separated strings
    for list_field in ["bullet_points", "search_terms", "additional_image_urls"]:
        if list_field in update_data and isinstance(update_data[list_field], list):
            update_data[list_field] = ",".join(update_data[list_field])

    for field, value in update_data.items():
        setattr(listing, field, value)

    db.add(listing)
    await db.flush()
    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a listing."""
    result = await db.execute(
        select(Listing).where(
            Listing.id == listing_id,
            Listing.owner_id == current_user.id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    await db.delete(listing)
    await db.flush()


@router.post("/{listing_id}/publish")
async def publish_listing(
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a listing as published."""
    result = await db.execute(
        select(Listing).where(
            Listing.id == listing_id,
            Listing.owner_id == current_user.id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    listing.status = ListingStatus.PUBLISHED
    listing.published_at = func.now()
    db.add(listing)
    await db.flush()

    return {"message": "Listing published successfully", "id": listing.id}
