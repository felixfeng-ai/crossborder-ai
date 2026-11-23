"""个人工作区账务回填测试。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.workspace_billing_backfill import (
    backfill_personal_workspace_billing,
)
from app.services.workspaces import ensure_personal_workspace


async def _create_user_with_personal(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    return user, workspace


@pytest.mark.asyncio
async def test_backfill_copies_wallet_and_subscription_idempotently(db_session):
    now = datetime.now(timezone.utc)
    user, workspace = await _create_user_with_personal(
        db_session,
        "billing-backfill@example.com",
    )
    db_session.add(
        CreditWallet(
            user_id=user.id,
            plan_credits=800,
            purchased_credits=20,
        )
    )
    subscription = UserSubscription(
        user_id=user.id,
        plan="standard",
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=30),
        source="manual_transfer",
    )
    db_session.add(subscription)
    await db_session.commit()

    dry_run = await backfill_personal_workspace_billing(
        db_session,
        dry_run=True,
        now=now,
    )
    assert dry_run["wallets"]["would_create"] == 1
    assert dry_run["subscriptions"]["would_create"] == 1
    assert (
        await db_session.execute(
            select(WorkspaceCreditWallet).where(
                WorkspaceCreditWallet.workspace_id == workspace.id
            )
        )
    ).scalar_one_or_none() is None

    first = await backfill_personal_workspace_billing(
        db_session,
        now=now,
    )
    wallet = (
        await db_session.execute(
            select(WorkspaceCreditWallet).where(
                WorkspaceCreditWallet.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    workspace_subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert first["wallets"]["created"] == 1
    assert first["subscriptions"]["created"] == 1
    assert wallet.plan_credits == 800
    assert wallet.purchased_credits == 20
    assert workspace_subscription.plan == "standard"
    assert workspace_subscription.payer_user_id == user.id
    assert workspace_subscription.expires_at.replace(
        tzinfo=timezone.utc
    ) == subscription.expires_at

    second = await backfill_personal_workspace_billing(
        db_session,
        now=now,
    )
    assert second["wallets"]["created"] == 0
    assert second["wallets"]["skipped"] == 1
    assert second["subscriptions"]["created"] == 0
    assert second["subscriptions"]["skipped"] == 1


@pytest.mark.asyncio
async def test_backfill_reports_conflicts_without_overwriting(db_session):
    now = datetime.now(timezone.utc)
    user, workspace = await _create_user_with_personal(
        db_session,
        "billing-backfill-conflict@example.com",
    )
    db_session.add(
        CreditWallet(
            user_id=user.id,
            plan_credits=800,
            purchased_credits=20,
        )
    )
    db_session.add(
        UserSubscription(
            user_id=user.id,
            plan="standard",
            status="active",
            starts_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    db_session.add(
        WorkspaceSubscription(
            workspace_id=workspace.id,
            plan="professional",
            status="active",
            starts_at=now,
            expires_at=now + timedelta(days=60),
            payer_user_id=user.id,
        )
    )
    await db_session.commit()

    report = await backfill_personal_workspace_billing(
        db_session,
        now=now,
    )
    wallet = (
        await db_session.execute(
            select(WorkspaceCreditWallet).where(
                WorkspaceCreditWallet.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert report["wallets"]["conflicts"] == 1
    assert report["subscriptions"]["conflicts"] == 1
    assert wallet.plan_credits == 1
    assert wallet.purchased_credits == 2
    assert subscription.plan == "professional"
