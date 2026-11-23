"""个人账务持续同步测试。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.plan_service import (
    apply_monthly_allowance,
    expire_due_subscriptions,
    grant_purchased_credits,
)
from app.services.workspace_billing import get_or_create_workspace_wallet
from app.services.workspaces import ensure_personal_workspace


async def _user_with_personal(
    db_session,
    email: str,
    *,
    plan: str,
    plan_credits: int,
    purchased_credits: int,
):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
        plan=plan,
        credits=plan_credits + purchased_credits,
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add(
        CreditWallet(
            user_id=user.id,
            plan_credits=plan_credits,
            purchased_credits=purchased_credits,
        )
    )
    await db_session.commit()
    return user, workspace


@pytest.mark.asyncio
async def test_monthly_allowance_syncs_personal_wallet_and_subscription(
    db_session,
):
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    user, workspace = await _user_with_personal(
        db_session,
        "personal-ledger-monthly@example.com",
        plan="professional",
        plan_credits=30,
        purchased_credits=5,
    )
    user.credit_period_start = now - timedelta(days=40)
    await db_session.flush()

    transaction = await apply_monthly_allowance(db_session, user, now=now)
    wallet = await get_or_create_workspace_wallet(db_session, workspace)
    await db_session.refresh(wallet)
    subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert transaction is not None
    assert transaction.workspace_id == workspace.id
    assert wallet.plan_credits == 3000
    assert wallet.purchased_credits == 5
    assert subscription.plan == "professional"
    assert subscription.expires_at.replace(
        tzinfo=timezone.utc
    ) == now + timedelta(days=30)


@pytest.mark.asyncio
async def test_purchased_credit_grant_syncs_personal_wallet(db_session):
    user, workspace = await _user_with_personal(
        db_session,
        "personal-ledger-grant@example.com",
        plan="free",
        plan_credits=30,
        purchased_credits=0,
    )

    await grant_purchased_credits(
        db_session,
        user,
        200,
        reference_type="credit_purchase",
        reference_id="personal-order-1",
    )
    wallet = await get_or_create_workspace_wallet(db_session, workspace)
    await db_session.refresh(wallet)
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.reference_id == "personal-order-1"
            )
        )
    ).scalar_one()

    assert wallet.plan_credits == 30
    assert wallet.purchased_credits == 200
    assert transaction.workspace_id == workspace.id
    assert transaction.actor_user_id == user.id


@pytest.mark.asyncio
async def test_expired_subscription_syncs_personal_workspace(db_session):
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    user, workspace = await _user_with_personal(
        db_session,
        "personal-ledger-expire@example.com",
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
    db_session.add(
        WorkspaceSubscription(
            workspace_id=workspace.id,
            plan="professional",
            status="active",
            starts_at=now - timedelta(days=31),
            expires_at=now - timedelta(seconds=1),
            payer_user_id=user.id,
        )
    )
    await db_session.flush()

    expired = await expire_due_subscriptions(db_session, now=now)
    wallet = await get_or_create_workspace_wallet(db_session, workspace)
    await db_session.refresh(wallet)
    workspace_subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id
            )
        )
    ).scalar_one()

    assert expired == 1
    assert wallet.plan_credits == 30
    assert wallet.purchased_credits == 50
    assert workspace_subscription.status == "expired"
