"""兼容旧调用点的积分服务入口。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.plan_service import (
    PLAN_CATALOG,
    add_purchased_credits,
    apply_monthly_allowance,
)


PLAN_MONTHLY_CREDITS = {
    plan: int(config["monthly_credits"])
    for plan, config in PLAN_CATALOG.items()
}


async def add_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    *,
    feature: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    description: str = "",
) -> int:
    """兼容退款/补偿调用，统一进入购买积分钱包。"""
    return await add_purchased_credits(
        db,
        user,
        amount,
        feature=feature,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )


__all__ = [
    "PLAN_MONTHLY_CREDITS",
    "add_credits",
    "apply_monthly_allowance",
]
