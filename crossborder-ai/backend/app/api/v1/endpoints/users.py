"""v1 用户资料与账户接口。

VeyaShip - User Management Endpoints.

Profile retrieval, update, and admin user listing."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_active_superuser, PaginationParams
from app.models.user import User
from app.schemas.user import UserProfile, UserResponse, UserUpdate
from app.schemas.product import ProductListResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/profile", response_model=UserProfile)
async def get_profile(
    current_user: User = Depends(get_current_user),
):
    """Get the current user's full profile."""
    return current_user


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.add(current_user)
    await db.flush()
    return current_user


@router.get("/credits")
async def get_credits(
    current_user: User = Depends(get_current_user),
):
    """Get the current user's credit balance."""
    return {
        "credits_remaining": current_user.credits_remaining,
        "credits_total": current_user.credits_total,
        "usage_percentage": round(
            ((current_user.credits_total - current_user.credits_remaining)
             / max(current_user.credits_total, 1)) * 100, 1
        ),
    }


# --- Admin Endpoints ---
@router.get("/admin/users", response_model=list[UserResponse])
async def list_all_users(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_superuser),
):
    """Admin: List all users with pagination."""
    result = await db.execute(
        select(User).offset(pagination.offset).limit(pagination.limit)
    )
    return result.scalars().all()
