"""v1 分析与仪表盘接口。

VeyaShip - Analytics & Dashboard Endpoints.

Usage statistics, generation metrics, and dashboard data."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.product import Product
from app.models.listing import Listing, ListingStatus
from app.models.content import ContentGeneration, ContentStatus

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated dashboard metrics for the current user."""
    user_id = current_user.id

    # Product count
    product_count = (
        await db.execute(
            select(func.count(Product.id)).where(Product.owner_id == user_id)
        )
    ).scalar()

    # Listing counts by status
    draft_listings = (
        await db.execute(
            select(func.count(Listing.id)).where(
                Listing.owner_id == user_id,
                Listing.status == ListingStatus.DRAFT,
            )
        )
    ).scalar()

    published_listings = (
        await db.execute(
            select(func.count(Listing.id)).where(
                Listing.owner_id == user_id,
                Listing.status == ListingStatus.PUBLISHED,
            )
        )
    ).scalar()

    # Content generation stats
    total_generations = (
        await db.execute(
            select(func.count(ContentGeneration.id)).where(
                ContentGeneration.user_id == user_id
            )
        )
    ).scalar()

    # Generations in last 7 days
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_generations = (
        await db.execute(
            select(func.count(ContentGeneration.id)).where(
                ContentGeneration.user_id == user_id,
                ContentGeneration.created_at >= week_ago,
            )
        )
    ).scalar()

    # Platform distribution
    platform_query = await db.execute(
        select(Listing.platform, func.count(Listing.id))
        .where(Listing.owner_id == user_id)
        .group_by(Listing.platform)
    )
    platform_distribution = {
        row[0].value if hasattr(row[0], "value") else row[0]: row[1]
        for row in platform_query.all()
    }

    return {
        "products": {
            "total": product_count or 0,
        },
        "listings": {
            "draft": draft_listings or 0,
            "published": published_listings or 0,
            "total": (draft_listings or 0) + (published_listings or 0),
        },
        "content": {
            "total_generations": total_generations or 0,
            "recent_7_days": recent_generations or 0,
            "credits_remaining": current_user.credits_remaining,
            "credits_used": current_user.credits_total - current_user.credits_remaining,
        },
        "platforms": platform_distribution,
    }


@router.get("/usage-trend")
async def get_usage_trend(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily content generation usage for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            cast(ContentGeneration.created_at, Date).label("date"),
            func.count(ContentGeneration.id).label("count"),
        )
        .where(
            ContentGeneration.user_id == current_user.id,
            ContentGeneration.created_at >= since,
        )
        .group_by(cast(ContentGeneration.created_at, Date))
        .order_by("date")
    )

    trend = [{"date": str(row.date), "count": row.count} for row in result.all()]

    return {
        "days": days,
        "trend": trend,
        "total": sum(item["count"] for item in trend),
    }
