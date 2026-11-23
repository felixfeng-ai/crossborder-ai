"""个人扣费工作区镜像测试。"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.services.workspace_billing import (
    deduct_workspace_credits,
    get_or_create_workspace_wallet,
    workspace_wallet_total,
)
from app.services.workspaces import ensure_personal_workspace


async def _user_with_personal(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
        credits=10,
    )
    db_session.add(user)
    await db_session.flush()
    personal = await ensure_personal_workspace(db_session, user)
    db_session.add(
        CreditWallet(
            user_id=user.id,
            plan_credits=10,
            purchased_credits=0,
        )
    )
    await db_session.commit()
    return user, personal


async def _team_workspace(db_session, user: User) -> Workspace:
    workspace = Workspace(
        name="Deduction Team",
        slug=f"deduction-team-{uuid4().hex[:12]}",
        type="team",
        owner_user_id=user.id,
        status="active",
        settings_json="{}",
    )
    db_session.add(workspace)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
    )
    await db_session.commit()
    return workspace


@pytest.mark.asyncio
async def test_deduct_credits_mirrors_explicit_personal_workspace(db_session):
    user, personal = await _user_with_personal(
        db_session,
        "personal-deduction@example.com",
    )

    remaining = await user.deduct_credits(
        db_session,
        3,
        workspace_id=personal.id,
        actor_user_id=user.id,
        feature="personal_test",
    )
    wallet = await get_or_create_workspace_wallet(db_session, personal)
    await db_session.refresh(wallet)
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.feature == "personal_test"
            )
        )
    ).scalar_one()

    assert remaining == 7
    assert user.credits == 7
    assert workspace_wallet_total(wallet) == 7
    assert transaction.workspace_id == personal.id
    assert transaction.actor_user_id == user.id


@pytest.mark.asyncio
async def test_deduct_credits_resolves_personal_workspace_automatically(
    db_session,
):
    user, personal = await _user_with_personal(
        db_session,
        "personal-deduction-auto@example.com",
    )

    await user.deduct_credits(
        db_session,
        2,
        feature="legacy_call",
    )
    wallet = await get_or_create_workspace_wallet(db_session, personal)
    await db_session.refresh(wallet)
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.feature == "legacy_call"
            )
        )
    ).scalar_one()

    assert wallet.plan_credits == 8
    assert transaction.workspace_id == personal.id
    assert transaction.actor_user_id == user.id


@pytest.mark.asyncio
async def test_deduct_workspace_credits_personal_reuses_user_wallet(
    db_session,
):
    user, personal = await _user_with_personal(
        db_session,
        "personal-deduction-bridge@example.com",
    )

    remaining = await deduct_workspace_credits(
        db_session,
        workspace=personal,
        actor_user_id=user.id,
        amount=4,
        feature="bridge_test",
    )
    wallet = await get_or_create_workspace_wallet(db_session, personal)
    await db_session.refresh(wallet)

    assert remaining == 6
    assert user.credits == 6
    assert workspace_wallet_total(wallet) == 6


@pytest.mark.asyncio
async def test_team_deduction_still_does_not_touch_personal_mirror(db_session):
    user, personal = await _user_with_personal(
        db_session,
        "personal-deduction-team@example.com",
    )
    team = await _team_workspace(db_session, user)
    team_wallet = await get_or_create_workspace_wallet(db_session, team)
    team_wallet.plan_credits = 5
    await db_session.commit()

    await deduct_workspace_credits(
        db_session,
        workspace=team,
        actor_user_id=user.id,
        amount=2,
        feature="team_test",
    )
    personal_wallet = await get_or_create_workspace_wallet(db_session, personal)
    await db_session.refresh(personal_wallet)
    await db_session.refresh(user)

    assert user.credits == 10
    assert personal_wallet.plan_credits == 0
