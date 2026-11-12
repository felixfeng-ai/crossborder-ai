"""套餐双钱包、有效期、积分包和免费额度测试。"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.feature_usage import FeatureUsageCounter
from app.models.subscription import UserSubscription
from app.models.user import User
from app.services.plan_service import (
    PLAN_CATALOG,
    activate_paid_plan,
    apply_monthly_allowance,
    consume_feature_allowance,
    expire_due_subscriptions,
    grant_purchased_credits,
)


async def _user_with_wallet(
    db_session,
    *,
    plan: str = "standard",
    plan_credits: int = 5,
    purchased_credits: int = 0,
) -> tuple[User, CreditWallet]:
    user = User(
        id=uuid.uuid4(),
        email=f"wallet-{uuid.uuid4().hex[:8]}@example.com",
        username="wallet-user",
        password_hash="x",
        plan=plan,
        credits=plan_credits + purchased_credits,
    )
    db_session.add(user)
    await db_session.flush()
    wallet = CreditWallet(
        user_id=user.id,
        plan_credits=plan_credits,
        purchased_credits=purchased_credits,
    )
    db_session.add(wallet)
    await db_session.flush()
    return user, wallet


def test_plan_catalog_uses_cost_sustainable_defaults():
    assert PLAN_CATALOG["free"]["monthly_credits"] == 30
    assert PLAN_CATALOG["standard"]["monthly_credits"] == 800
    assert PLAN_CATALOG["professional"]["monthly_credits"] == 3000
    assert PLAN_CATALOG["standard"]["valid_days"] == 30
    assert PLAN_CATALOG["professional"]["valid_days"] == 30


@pytest.mark.asyncio
async def test_deduct_uses_plan_credits_before_purchased(db_session):
    user, wallet = await _user_with_wallet(
        db_session,
        plan_credits=3,
        purchased_credits=10,
    )

    remaining = await user.deduct_credits(db_session, 5, feature="test_spend")

    await db_session.refresh(wallet)
    assert remaining == 8
    assert wallet.plan_credits == 0
    assert wallet.purchased_credits == 8
    assert user.credits == 8


@pytest.mark.asyncio
async def test_monthly_allowance_preserves_purchased_credits(db_session):
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    user, wallet = await _user_with_wallet(
        db_session,
        plan_credits=0,
        purchased_credits=8,
    )
    await apply_monthly_allowance(
        db_session,
        user,
        now=now,
        force=True,
    )

    await db_session.refresh(wallet)
    assert wallet.plan_credits == 800
    assert wallet.purchased_credits == 8
    assert user.credits == 808


@pytest.mark.asyncio
async def test_activate_paid_plan_sets_expiry_and_quota(db_session):
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    user, wallet = await _user_with_wallet(
        db_session,
        plan="free",
        plan_credits=30,
        purchased_credits=12,
    )

    subscription = await activate_paid_plan(
        db_session,
        user,
        "standard",
        now=now,
    )
    await db_session.refresh(wallet)

    assert subscription.expires_at == now + timedelta(days=30)
    assert subscription.status == "active"
    assert user.plan == "standard"
    assert wallet.plan_credits == 800
    assert wallet.purchased_credits == 12
    assert user.credits == 812


@pytest.mark.asyncio
async def test_professional_without_subscription_reconciles_to_full_allowance(
    db_session,
):
    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    user, wallet = await _user_with_wallet(
        db_session,
        plan="professional",
        plan_credits=30,
        purchased_credits=0,
    )
    user.credit_period_start = now
    await db_session.flush()

    await apply_monthly_allowance(db_session, user, now=now)
    await db_session.refresh(wallet)
    subscription = (
        await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert subscription.plan == "professional"
    assert subscription.source == "automatic_plan_reconciliation"
    assert wallet.plan_credits == 3000
    assert user.credits == 3000
    assert user.credit_period_start == now


@pytest.mark.asyncio
async def test_same_active_plan_does_not_refill_spent_plan_credits(db_session):
    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    user, wallet = await _user_with_wallet(
        db_session,
        plan="professional",
        plan_credits=30,
        purchased_credits=5,
    )
    user.credit_period_start = now
    db_session.add(
        UserSubscription(
            user_id=user.id,
            plan="professional",
            status="active",
            starts_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=28),
        )
    )
    await db_session.flush()

    result = await apply_monthly_allowance(db_session, user, now=now)
    await db_session.refresh(wallet)

    assert result is None
    assert wallet.plan_credits == 30
    assert wallet.purchased_credits == 5


@pytest.mark.asyncio
async def test_legacy_excess_plan_credits_are_reclassified_as_purchased(
    db_session,
):
    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    user, wallet = await _user_with_wallet(
        db_session,
        plan="professional",
        plan_credits=99_998,
        purchased_credits=0,
    )
    user.credit_period_start = now
    db_session.add(
        UserSubscription(
            user_id=user.id,
            plan="professional",
            status="active",
            starts_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=28),
            source="migration_grandfather",
        )
    )
    await db_session.flush()

    transaction = await apply_monthly_allowance(db_session, user, now=now)
    await db_session.refresh(wallet)

    assert transaction is not None
    assert transaction.feature == "legacy_plan_credit_reclassification"
    assert wallet.plan_credits == 3_000
    assert wallet.purchased_credits == 96_998
    assert user.credits == 99_998


@pytest.mark.asyncio
async def test_expired_subscription_downgrades_but_keeps_purchased(db_session):
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    user, wallet = await _user_with_wallet(
        db_session,
        plan="professional",
        plan_credits=100,
        purchased_credits=50,
    )
    db_session.add(
        UserSubscription(
            user_id=user.id,
            plan="professional",
            status="active",
            starts_at=now - timedelta(days=31),
            expires_at=now - timedelta(seconds=1),
        )
    )
    await db_session.flush()

    expired = await expire_due_subscriptions(db_session, now=now)
    await db_session.refresh(user)
    await db_session.refresh(wallet)

    assert expired == 1
    assert user.plan == "free"
    assert wallet.plan_credits == 30
    assert wallet.purchased_credits == 50
    assert user.credits == 80


@pytest.mark.asyncio
async def test_analysis_included_quota_then_overage_credit(db_session):
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    user, _wallet = await _user_with_wallet(
        db_session,
        plan="free",
        plan_credits=30,
        purchased_credits=0,
    )

    for _ in range(10):
        result = await consume_feature_allowance(
            db_session,
            user,
            "category_analysis",
            now=now,
        )
        assert result["charged"] == 0

    overage = await consume_feature_allowance(
        db_session,
        user,
        "category_analysis",
        now=now,
    )
    await db_session.refresh(user)
    assert overage["charged"] == 1
    assert user.credits == 29
    counter = (
        await db_session.execute(
            select(FeatureUsageCounter).where(
                FeatureUsageCounter.user_id == user.id,
                FeatureUsageCounter.feature == "category_analysis",
            )
        )
    ).scalar_one()
    assert counter.used == 11


@pytest.mark.asyncio
async def test_grant_purchased_credits_is_idempotent_by_reference(db_session):
    user, wallet = await _user_with_wallet(
        db_session,
        plan="free",
        plan_credits=30,
    )

    first = await grant_purchased_credits(
        db_session,
        user,
        200,
        reference_type="credit_purchase",
        reference_id="order-1",
    )
    second = await grant_purchased_credits(
        db_session,
        user,
        200,
        reference_type="credit_purchase",
        reference_id="order-1",
    )

    await db_session.refresh(wallet)
    assert first == 200
    assert second == 0
    assert wallet.purchased_credits == 200
    assert user.credits == 230
    count = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.reference_id == "order-1",
                CreditTransaction.feature == "credit_pack_purchase",
            )
        )
    ).scalars().all()
    assert len(count) == 1
