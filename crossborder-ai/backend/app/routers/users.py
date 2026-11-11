"""VeyaShip - User Management Routes.

Credits query and deduction endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.services.credit_service import apply_monthly_allowance
from pydantic import BaseModel, Field

router = APIRouter(prefix="/users", tags=["Users"])


class DeductCreditsRequest(BaseModel):
    amount: int = Field(..., ge=1, description="扣减积分数")


@router.get("/credits")
async def get_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's credit balance."""
    applied = await apply_monthly_allowance(db, current_user)
    if applied is not None:
        await db.commit()
        await db.refresh(current_user)
    return {
        "credits": current_user.credits,
    }


@router.get("/credits/transactions")
async def list_credit_transactions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户的积分流水，最新在前。"""
    safe_limit = max(1, min(limit, 200))
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == current_user.id)
        .order_by(desc(CreditTransaction.created_at))
        .limit(safe_limit)
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "delta": item.delta,
                "balance_after": item.balance_after,
                "feature": item.feature,
                "reference_type": item.reference_type,
                "reference_id": item.reference_id,
                "description": item.description,
                "created_at": str(item.created_at),
            }
            for item in result.scalars().all()
        ]
    }


@router.post("/credits/deduct")
async def deduct_credits(
    payload: DeductCreditsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deduct credits atomically.

    Uses row-level locking to prevent race conditions.
    Returns 400 if credits are insufficient.
    """
    try:
        remaining = await current_user.deduct_credits(
            db,
            payload.amount,
            feature="manual_deduct",
            description="手动扣减积分",
        )
        await db.commit()
        return {
            "success": True,
            "credits_deducted": payload.amount,
            "credits_remaining": remaining,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
