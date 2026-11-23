"""个人账务切换工作区单一事实源测试。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.plan_service import (
    add_purchased_credits,
    apply_monthly_allowance,
    expire_due_subscriptions,
    get_active_subscription,
    get_or_create_wallet,
)
from app.services.workspaces import ensure_personal_workspace


@pytest.mark.asyncio
async def test_personal_deduction_uses_workspace_wallet_as_authority(db_session):
    user = User(
        email="single-source-deduction@example.com",
        username="single-source-deduction",
        password_hash="not-used",
        plan="standard",
        credits=10,
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add_all(
        [
            CreditWallet(
                user_id=user.id,
                plan_credits=10,
                purchased_credits=0,
            ),
            WorkspaceCreditWallet(
                workspace_id=workspace.id,
                plan_credits=2,
                purchased_credits=0,
            ),
        ]
    )
    await db_session.commit()

    remaining = await user.deduct_credits(
        db_session,
        1,
        feature="single_source_spend",
    )
    await db_session.commit()
    await db_session.refresh(user)
    mirror = await db_session.get(CreditWallet, user.id)
    workspace_wallet = await db_session.get(
        WorkspaceCreditWallet,
        workspace.id,
    )

    assert remaining == 1
    assert workspace_wallet.plan_credits == 1
    assert mirror.plan_credits == 1
    assert user.credits == 1


@pytest.mark.asyncio
async def test_personal_credit_grant_updates_workspace_then_mirror(db_session):
    user = User(
        email="single-source-grant@example.com",
        username="single-source-grant",
        password_hash="not-used",
        plan="standard",
        credits=100,
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add_all(
        [
            CreditWallet(
                user_id=user.id,
                plan_credits=100,
                purchased_credits=0,
            ),
            WorkspaceCreditWallet(
                workspace_id=workspace.id,
                plan_credits=5,
                purchased_credits=1,
            ),
        ]
    )
    await db_session.commit()

    total = await add_purchased_credits(
        db_session,
        user,
        10,
        feature="single_source_grant",
        reference_type="manual",
        reference_id="single-source-grant",
    )
    mirror = await get_or_create_wallet(db_session, user)
    workspace_wallet = await db_session.get(
        WorkspaceCreditWallet,
        workspace.id,
    )

    assert total == 16
    assert workspace_wallet.plan_credits == 5
    assert workspace_wallet.purchased_credits == 11
    assert mirror.plan_credits == 5
    assert mirror.purchased_credits == 11
    assert user.credits == 16


@pytest.mark.asyncio
async def test_monthly_allowance_uses_workspace_subscription_and_wallet(
    db_session,
):
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    user = User(
        email="single-source-monthly@example.com",
        username="single-source-monthly",
        password_hash="not-used",
        plan="free",
        credits=30,
        credit_period_start=now - timedelta(days=40),
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add_all(
        [
            CreditWallet(
                user_id=user.id,
                plan_credits=30,
                purchased_credits=0,
            ),
            WorkspaceCreditWallet(
                workspace_id=workspace.id,
                plan_credits=7,
                purchased_credits=5,
            ),
            WorkspaceSubscription(
                workspace_id=workspace.id,
                plan="professional",
                status="active",
                starts_at=now - timedelta(days=2),
                expires_at=now + timedelta(days=28),
                payer_user_id=user.id,
            ),
        ]
    )
    await db_session.commit()

    transaction = await apply_monthly_allowance(
        db_session,
        user,
        now=now,
        force=True,
    )
    workspace_wallet = await db_session.get(
        WorkspaceCreditWallet,
        workspace.id,
    )
    mirror = await db_session.get(CreditWallet, user.id)
    legacy_subscription = (
        await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert transaction is not None
    assert workspace_wallet.plan_credits == 3000
    assert workspace_wallet.purchased_credits == 5
    assert mirror.plan_credits == 3000
    assert mirror.purchased_credits == 5
    assert user.plan == "professional"
    assert user.credits == 3005
    assert legacy_subscription.plan == "professional"


@pytest.mark.asyncio
async def test_legacy_balance_endpoints_read_workspace_authority(
    client,
    db_session,
):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "single-source-read@example.com",
            "username": "single-source-read",
            "password": "testpass123",
        },
    )
    assert registered.status_code == 201
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}"
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "single-source-read@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    user.credits = 50
    user.credit_period_start = datetime.now(timezone.utc)
    workspace_wallet = await db_session.get(
        WorkspaceCreditWallet,
        workspace.id,
    )
    assert workspace_wallet is not None
    workspace_wallet.plan_credits = 2
    workspace_wallet.purchased_credits = 3
    await db_session.commit()

    legacy_response = await client.get(
        "/api/v1/users/credits",
        headers=headers,
    )
    wallet_response = await client.get(
        "/api/v1/billing/wallet",
        headers=headers,
    )

    assert legacy_response.status_code == 200
    assert legacy_response.json()["credits"] == 5
    assert wallet_response.status_code == 200
    assert wallet_response.json()["plan_credits"] == 2
    assert wallet_response.json()["purchased_credits"] == 3
    assert wallet_response.json()["total_credits"] == 5


@pytest.mark.asyncio
async def test_workspace_subscription_expires_and_mirrors_legacy_plan(
    db_session,
):
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    user = User(
        email="single-source-expire@example.com",
        username="single-source-expire",
        password_hash="not-used",
        plan="professional",
        credits=150,
        credit_period_start=now - timedelta(days=10),
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add_all(
        [
            CreditWallet(
                user_id=user.id,
                plan_credits=100,
                purchased_credits=50,
            ),
            WorkspaceCreditWallet(
                workspace_id=workspace.id,
                plan_credits=100,
                purchased_credits=50,
            ),
            WorkspaceSubscription(
                workspace_id=workspace.id,
                plan="professional",
                status="active",
                starts_at=now - timedelta(days=31),
                expires_at=now - timedelta(seconds=1),
                payer_user_id=user.id,
            ),
        ]
    )
    await db_session.commit()

    expired = await expire_due_subscriptions(db_session, now=now)
    workspace_wallet = await db_session.get(
        WorkspaceCreditWallet,
        workspace.id,
    )
    mirror = await db_session.get(CreditWallet, user.id)
    legacy_subscription = (
        await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id
            )
        )
    ).scalar_one()

    assert expired == 1
    assert workspace_wallet.plan_credits == 30
    assert workspace_wallet.purchased_credits == 50
    assert mirror.plan_credits == 30
    assert mirror.purchased_credits == 50
    assert user.plan == "free"
    assert user.credits == 80
    assert legacy_subscription.status == "expired"


@pytest.mark.asyncio
async def test_active_workspace_subscription_mirrors_to_legacy_reader(
    db_session,
):
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    user = User(
        email="single-source-subscription-read@example.com",
        username="single-source-subscription-read",
        password_hash="not-used",
        plan="free",
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    workspace_subscription = WorkspaceSubscription(
        workspace_id=workspace.id,
        plan="standard",
        status="active",
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
        payer_user_id=user.id,
    )
    db_session.add(workspace_subscription)
    await db_session.commit()

    legacy = await get_active_subscription(db_session, user.id, now=now)

    assert legacy is not None
    assert legacy.plan == "standard"
    assert legacy.expires_at.replace(tzinfo=timezone.utc) == (
        workspace_subscription.expires_at
    )
    assert user.plan == "standard"


@pytest.mark.asyncio
async def test_workspace_credit_period_prevents_duplicate_refill(db_session):
    now = datetime(2026, 12, 15, tzinfo=timezone.utc)
    user = User(
        email="single-source-period@example.com",
        username="single-source-period",
        password_hash="not-used",
        plan="professional",
        credits=3005,
        credit_period_start=now - timedelta(days=40),
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    workspace_wallet = WorkspaceCreditWallet(
        workspace_id=workspace.id,
        plan_credits=7,
        purchased_credits=5,
        credit_period_start=now,
    )
    db_session.add(workspace_wallet)
    db_session.add(
        WorkspaceSubscription(
            workspace_id=workspace.id,
            plan="professional",
            status="active",
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
            payer_user_id=user.id,
        )
    )
    await db_session.commit()

    transaction = await apply_monthly_allowance(db_session, user, now=now)

    assert transaction is None
    assert workspace_wallet.plan_credits == 7
    assert workspace_wallet.purchased_credits == 5
    assert user.credit_period_start == now
