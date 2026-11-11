"""套餐、双钱包、有效期和功能免费额度。"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.feature_usage import FeatureUsageCounter
from app.models.subscription import UserSubscription
from app.models.user import User


PLAN_CATALOG: dict[str, dict] = {
    "free": {
        "name": "Free",
        "price": 0,
        "monthly_credits": 30,
        "valid_days": 0,
    },
    "standard": {
        "name": "Standard",
        "price": 99,
        "monthly_credits": 800,
        "valid_days": 30,
    },
    "professional": {
        "name": "Professional",
        "price": 249,
        "monthly_credits": 2000,
        "valid_days": 30,
    },
}

CREDIT_PACKS = (
    {"id": "pack_200", "name": "入门积分包", "credits": 200, "price": 19},
    {"id": "pack_500", "name": "常用积分包", "credits": 500, "price": 45},
    {"id": "pack_1200", "name": "专业积分包", "credits": 1200, "price": 99},
)

ANALYSIS_LIMITS = {
    "category_analysis": 10,
    "ai_insights": 10,
}

MANUAL_STORE_CHECK_LIMITS = {
    "free": 0,
    "standard": 10,
    "professional": 20,
}


async def get_or_create_wallet(
    db: AsyncSession,
    user: User,
    *,
    lock: bool = False,
) -> CreditWallet:
    query = select(CreditWallet).where(CreditWallet.user_id == user.id)
    if lock:
        query = query.with_for_update()
    wallet = (await db.execute(query)).scalar_one_or_none()
    if wallet is None:
        initial_credits = max(0, int(user.credits or 0))
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(CreditWallet).values(
                user_id=user.id,
                plan_credits=initial_credits,
                purchased_credits=0,
            ).on_conflict_do_nothing(index_elements=["user_id"])
        elif dialect == "sqlite":
            statement = sqlite_insert(CreditWallet).values(
                user_id=user.id,
                plan_credits=initial_credits,
                purchased_credits=0,
            ).on_conflict_do_nothing(index_elements=["user_id"])
        else:
            statement = insert(CreditWallet).values(
                user_id=user.id,
                plan_credits=initial_credits,
                purchased_credits=0,
            )
        await db.execute(statement)
        await db.flush()
        wallet = (
            await db.execute(
                select(CreditWallet)
                .where(CreditWallet.user_id == user.id)
                .with_for_update() if lock else select(CreditWallet).where(CreditWallet.user_id == user.id)
            )
        ).scalar_one()
    return wallet


def wallet_total(wallet: CreditWallet) -> int:
    return int(wallet.plan_credits or 0) + int(wallet.purchased_credits or 0)


async def apply_monthly_allowance(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> CreditTransaction | None:
    current = now or datetime.now(timezone.utc)
    if (
        not force
        and user.credit_period_start
        and user.credit_period_start.year == current.year
        and user.credit_period_start.month == current.month
    ):
        return None

    wallet = await get_or_create_wallet(db, user, lock=True)
    allowance = int(
        PLAN_CATALOG.get(user.plan, PLAN_CATALOG["free"])["monthly_credits"]
    )
    previous_total = wallet_total(wallet)
    wallet.plan_credits = allowance
    user.credit_period_start = current
    user.credits = wallet_total(wallet)

    transaction = CreditTransaction(
        user_id=user.id,
        delta=user.credits - previous_total,
        balance_after=user.credits,
        wallet_type="plan",
        feature="monthly_allowance",
        reference_type="plan",
        reference_id=user.plan,
        description=f"{user.plan} 套餐 {current:%Y-%m} 月度额度",
        metadata_json=json.dumps(
            {
                "plan": user.plan,
                "allowance": allowance,
                "purchased_credits": wallet.purchased_credits,
                "period": current.strftime("%Y-%m"),
            },
            ensure_ascii=False,
        ),
    )
    db.add(transaction)
    await db.flush()
    return transaction


async def add_purchased_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    *,
    feature: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    description: str = "",
) -> int:
    if amount <= 0:
        return user.credits
    wallet = await get_or_create_wallet(db, user, lock=True)
    wallet_total_before = wallet_total(wallet)
    mirrored_total = int(user.credits or 0)
    if mirrored_total > wallet_total_before:
        wallet.purchased_credits += mirrored_total - wallet_total_before
    elif mirrored_total < wallet_total_before:
        reduce = wallet_total_before - mirrored_total
        from_plan = min(int(wallet.plan_credits or 0), reduce)
        wallet.plan_credits -= from_plan
        wallet.purchased_credits -= reduce - from_plan
    wallet.purchased_credits += amount
    user.credits = wallet_total(wallet)
    db.add(
        CreditTransaction(
            user_id=user.id,
            delta=amount,
            balance_after=user.credits,
            wallet_type="purchased",
            feature=feature,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description or f"增加 {amount} 积分",
        )
    )
    await db.flush()
    return user.credits


async def grant_purchased_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    *,
    reference_type: str,
    reference_id: str,
) -> int:
    existing = (
        await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.wallet_type == "purchased",
                CreditTransaction.reference_type == reference_type,
                CreditTransaction.reference_id == reference_id,
                CreditTransaction.feature == "credit_pack_purchase",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return 0
    await add_purchased_credits(
        db,
        user,
        amount,
        feature="credit_pack_purchase",
        reference_type=reference_type,
        reference_id=reference_id,
        description="积分包到账",
    )
    return amount


async def activate_paid_plan(
    db: AsyncSession,
    user: User,
    plan: str,
    *,
    now: datetime | None = None,
    source: str = "manual_transfer",
) -> UserSubscription:
    settings = PLAN_CATALOG.get(plan)
    if not settings or plan == "free":
        raise ValueError("无效的付费套餐")
    current = now or datetime.now(timezone.utc)

    await db.execute(
        update(UserSubscription)
        .where(
            UserSubscription.user_id == user.id,
            UserSubscription.status == "active",
        )
        .values(status="replaced")
    )
    subscription = UserSubscription(
        user_id=user.id,
        plan=plan,
        status="active",
        starts_at=current,
        expires_at=current + timedelta(days=settings["valid_days"]),
        source=source,
    )
    db.add(subscription)
    user.plan = plan
    user.credit_period_start = None
    await apply_monthly_allowance(db, user, now=current, force=True)
    await db.flush()
    return subscription


async def expire_due_subscriptions(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(timezone.utc)
    subscriptions = (
        await db.execute(
            select(UserSubscription).where(
                UserSubscription.status == "active",
                UserSubscription.expires_at <= current,
            )
        )
    ).scalars().all()
    expired = 0
    for subscription in subscriptions:
        subscription.status = "expired"
        user = await db.get(User, subscription.user_id)
        if user is None:
            continue
        user.plan = "free"
        user.credit_period_start = None
        await apply_monthly_allowance(db, user, now=current, force=True)
        expired += 1
    await db.flush()
    return expired


async def get_active_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> UserSubscription | None:
    current = now or datetime.now(timezone.utc)
    return (
        await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > current,
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def has_active_paid_plan(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> bool:
    if user.plan not in {"standard", "professional"}:
        return False
    subscription = await get_active_subscription(db, user.id, now=now)
    # 兼容老测试/旧数据：付费 plan 还没有订阅记录时先视为有效，
    # 正式存量用户由迁移补 30 天订阅。
    return subscription is not None or user.credit_period_start is None


def _period_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def _included_limit(user: User, feature: str) -> int:
    if feature in ANALYSIS_LIMITS:
        return ANALYSIS_LIMITS[feature]
    if feature == "manual_store_check":
        return MANUAL_STORE_CHECK_LIMITS.get(user.plan, 0)
    return 0


async def consume_feature_allowance(
    db: AsyncSession,
    user: User,
    feature: str,
    *,
    now: datetime | None = None,
    overage_credits: int = 1,
) -> dict:
    current = now or datetime.now(timezone.utc)
    period = _period_key(current)
    counter = (
        await db.execute(
            select(FeatureUsageCounter)
            .where(
                FeatureUsageCounter.user_id == user.id,
                FeatureUsageCounter.feature == feature,
                FeatureUsageCounter.period_key == period,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if counter is None:
        counter = FeatureUsageCounter(
            user_id=user.id,
            feature=feature,
            period_key=period,
            used=0,
        )
        db.add(counter)
        await db.flush()

    limit = _included_limit(user, feature)
    included = counter.used < limit
    charged = 0
    if included:
        counter.used += 1
        await db.flush()
    else:
        await user.deduct_credits(
            db,
            overage_credits,
            feature=f"{feature}_overage",
            reference_type="usage_period",
            reference_id=period,
            description=f"{feature} 超出免费额度",
        )
        counter.used += 1
        charged = overage_credits
        await db.flush()
    return {
        "charged": charged,
        "used": counter.used,
        "included_limit": limit,
        "included_remaining": max(0, limit - counter.used),
        "period_key": period,
    }


def plan_wallet_response(user: User, wallet: CreditWallet, subscription: UserSubscription | None) -> dict:
    return {
        "plan": user.plan,
        "plan_credits": wallet.plan_credits,
        "purchased_credits": wallet.purchased_credits,
        "total_credits": wallet_total(wallet),
        "credit_period_start": str(user.credit_period_start) if user.credit_period_start else None,
        "plan_expires_at": str(subscription.expires_at) if subscription else None,
        "subscription_status": subscription.status if subscription else "free",
    }
