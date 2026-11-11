"""积分额度与流水服务。"""

import json
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.models.user import User


PLAN_MONTHLY_CREDITS = {
    "free": 30,
    "standard": 99_999,
    "professional": 99_999,
}


def _same_month(left: datetime | None, right: datetime) -> bool:
    return bool(
        left
        and left.year == right.year
        and left.month == right.month
    )


async def apply_monthly_allowance(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> CreditTransaction | None:
    """按自然月应用套餐额度；同一月份重复调用不重复发放。"""
    current = now or datetime.now(timezone.utc)
    if not force and _same_month(user.credit_period_start, current):
        return None

    allowance = PLAN_MONTHLY_CREDITS.get(user.plan, PLAN_MONTHLY_CREDITS["free"])
    previous = int(user.credits or 0)
    user.credits = allowance
    user.credit_period_start = current
    transaction = CreditTransaction(
        user_id=user.id,
        delta=allowance - previous,
        balance_after=allowance,
        feature="monthly_allowance",
        reference_type="plan",
        reference_id=user.plan,
        description=f"{user.plan} 套餐 {current:%Y-%m} 月度额度",
        metadata_json=json.dumps(
            {
                "plan": user.plan,
                "allowance": allowance,
                "period": current.strftime("%Y-%m"),
            },
            ensure_ascii=False,
        ),
    )
    db.add(transaction)
    await db.flush()
    return transaction


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
    """原子增加积分并写入流水，用于退款、补偿或管理员加积分。"""
    if amount <= 0:
        return user.credits
    result = await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(credits=User.credits + amount)
        .returning(User.credits)
    )
    remaining = int(result.scalar_one())
    user.credits = remaining
    db.add(
        CreditTransaction(
            user_id=user.id,
            delta=amount,
            balance_after=remaining,
            feature=feature,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description or f"增加 {amount} 积分",
        )
    )
    await db.flush()
    return remaining
