"""工作区积分钱包核心行为测试。"""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.credit_purchase import CreditPurchase
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.dependencies import require_admin
from app.main import app
from app.services.ai.deepseek import DeepSeekService
from tests.ai_mock_helpers import mock_listing_ai
from app.services.plan_service import get_or_create_wallet
from app.services.workspace_billing import (
    deduct_workspace_credits,
    get_or_create_workspace_wallet,
    grant_workspace_purchased_credits,
    workspace_wallet_total,
)
from app.services.workspaces import ensure_personal_workspace


BACKEND_DIR = Path(__file__).resolve().parents[1]


async def _register(client, db_session, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@", 1)[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    personal = await ensure_personal_workspace(db_session, user)
    return (
        {"Authorization": f"Bearer {response.json()['access_token']}"},
        user,
        personal,
    )


async def _team_workspace(db_session, user: User) -> Workspace:
    workspace = Workspace(
        name="Billing Team",
        slug=f"billing-team-{uuid4().hex[:12]}",
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


def _headers_for(headers: dict[str, str], workspace: Workspace):
    return {**headers, "X-Workspace-Id": str(workspace.id)}


@pytest.mark.asyncio
async def test_team_wallet_deduction_does_not_touch_personal_wallet(db_session):
    user = User(
        email="workspace-billing@example.com",
        username="workspace-billing",
        password_hash="not-used",
        credits=30,
    )
    db_session.add(user)
    await db_session.flush()
    personal = await ensure_personal_workspace(db_session, user)
    team = await _team_workspace(db_session, user)
    personal_wallet = await get_or_create_wallet(db_session, user, lock=True)
    personal_wallet.plan_credits = 30
    personal_wallet.purchased_credits = 0
    team_wallet = await get_or_create_workspace_wallet(db_session, team)
    team_wallet.plan_credits = 3
    team_wallet.purchased_credits = 5
    await db_session.commit()

    remaining = await deduct_workspace_credits(
        db_session,
        workspace=team,
        actor_user_id=user.id,
        amount=4,
        feature="test_spend",
    )
    await db_session.refresh(team_wallet)
    await db_session.refresh(personal_wallet)
    await db_session.refresh(user)

    assert remaining == 4
    assert workspace_wallet_total(team_wallet) == 4
    assert team_wallet.plan_credits == 0
    assert team_wallet.purchased_credits == 4
    assert workspace_wallet_total(personal_wallet) == 30
    assert user.credits == 30
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.workspace_id == team.id,
                CreditTransaction.feature == "test_spend",
            )
        )
    ).scalar_one()
    assert transaction.actor_user_id == user.id
    assert transaction.balance_after == 4
    assert transaction.delta == -4
    assert personal.id != team.id


@pytest.mark.asyncio
async def test_team_wallet_rejects_insufficient_balance(db_session):
    user = User(
        email="workspace-billing-low@example.com",
        username="workspace-billing-low",
        password_hash="not-used",
        credits=30,
    )
    db_session.add(user)
    await db_session.flush()
    await ensure_personal_workspace(db_session, user)
    team = await _team_workspace(db_session, user)
    wallet = await get_or_create_workspace_wallet(db_session, team)
    wallet.plan_credits = 1
    wallet.purchased_credits = 0
    workspace_id = team.id
    await db_session.commit()

    with pytest.raises(ValueError, match="积分不足"):
        await deduct_workspace_credits(
            db_session,
            workspace=team,
            actor_user_id=user.id,
            amount=2,
            feature="too_much",
        )
    await db_session.rollback()
    refreshing_workspace = await db_session.get(Workspace, workspace_id)
    assert refreshing_workspace is not None
    refreshed = await get_or_create_workspace_wallet(
        db_session,
        refreshing_workspace,
    )
    assert workspace_wallet_total(refreshed) == 1


@pytest.mark.asyncio
async def test_team_wallet_endpoint_and_content_charge_are_workspace_scoped(
    client,
    db_session,
    monkeypatch,
):
    headers, user, _personal = await _register(
        client,
        db_session,
        "workspace-billing-route@example.com",
    )
    team = await _team_workspace(db_session, user)
    team_headers = _headers_for(headers, team)
    team_wallet = await get_or_create_workspace_wallet(db_session, team)
    team_wallet.plan_credits = 10
    team_wallet.purchased_credits = 0
    user.credits = 30
    await db_session.commit()

    mock_listing_ai(
        monkeypatch,
        "Premium wireless earbuds with long battery life.",
    )
    product_response = await client.post(
        "/api/v1/products/manual",
        headers=team_headers,
        json={
            "title": "Billing listing product",
            "url": "https://example.com/products/billing-listing",
        },
    )
    product_id = product_response.json()["product"]["id"]

    wallet_response = await client.get(
        "/api/v1/billing/wallet",
        headers=team_headers,
    )
    generated = await client.post(
        "/api/v1/content/generate",
        headers=team_headers,
        json={
            "product_id": product_id,
            "platform": "amazon",
            "language": "en",
        },
    )

    assert wallet_response.status_code == 200
    assert wallet_response.json()["total_credits"] == 10
    assert generated.status_code == 200, generated.text
    await db_session.refresh(team_wallet)
    await db_session.refresh(user)
    assert workspace_wallet_total(team_wallet) == 9
    assert user.credits == 30


@pytest.mark.asyncio
async def test_team_credit_pack_is_owned_and_granted_to_team_wallet(
    client,
    db_session,
):
    headers, user, _personal = await _register(
        client,
        db_session,
        "workspace-credit-pack@example.com",
    )
    team = await _team_workspace(db_session, user)
    team_headers = _headers_for(headers, team)
    personal_credits_before = user.credits
    admin = User(
        email="workspace-credit-pack-admin@example.com",
        username="workspace-credit-pack-admin",
        password_hash="not-used",
    )
    db_session.add(admin)
    await db_session.commit()
    admin_headers = {"Authorization": f"Bearer admin:{admin.id}"}

    app.dependency_overrides[require_admin] = lambda: admin
    try:
        created = await client.post(
            "/api/v1/billing/credit-packs/purchase",
            headers=team_headers,
            json={"pack_id": "pack_200", "contact": "team-wx"},
        )
        assert created.status_code == 200, created.text
        purchase_id = created.json()["id"]
        purchase = await db_session.get(
            CreditPurchase,
            UUID(purchase_id),
        )
        assert purchase is not None
        assert purchase.workspace_id == team.id
        assert purchase.created_by_user_id == user.id

        approved = await client.post(
            f"/api/v1/billing/credit-packs/{purchase_id}/approve",
            headers=admin_headers,
            json={"note": "团队到账"},
        )
        assert approved.status_code == 200, approved.text
    finally:
        app.dependency_overrides.pop(require_admin, None)

    team_wallet = await get_or_create_workspace_wallet(db_session, team)
    await db_session.refresh(team_wallet)
    await db_session.refresh(user)
    assert team_wallet.purchased_credits == 200
    assert workspace_wallet_total(team_wallet) == 200
    assert user.credits == personal_credits_before
    transaction = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.workspace_id == team.id,
                CreditTransaction.reference_id == purchase.order_id,
            )
        )
    ).scalar_one()
    assert transaction.delta == 200
    assert transaction.actor_user_id == admin.id


@pytest.mark.asyncio
async def test_workspace_credit_grant_is_idempotent(db_session):
    user = User(
        email="workspace-grant@example.com",
        username="workspace-grant",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    team = await _team_workspace(db_session, user)

    first = await grant_workspace_purchased_credits(
        db_session,
        workspace=team,
        actor_user_id=user.id,
        amount=50,
        reference_type="credit_purchase",
        reference_id="GRANT-1",
    )
    second = await grant_workspace_purchased_credits(
        db_session,
        workspace=team,
        actor_user_id=user.id,
        amount=50,
        reference_type="credit_purchase",
        reference_id="GRANT-1",
    )
    wallet = await get_or_create_workspace_wallet(db_session, team)
    await db_session.refresh(wallet)

    assert first == 50
    assert second == 0
    assert wallet.purchased_credits == 50
    assert workspace_wallet_total(wallet) == 50


def test_workspace_billing_migration_adds_core_tables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workspace-billing-core.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "head")
    inspector = sa.inspect(engine)

    assert {
        "workspace_credit_wallets",
        "workspace_subscriptions",
        "billing_reconciliation_cases",
    } <= set(inspector.get_table_names())
    assert {
        "workspace_id",
        "actor_user_id",
    } <= {
        column["name"]
        for column in inspector.get_columns("credit_transactions")
    }
    assert {
        "workspace_id",
        "created_by_user_id",
    } <= {
        column["name"]
        for column in inspector.get_columns("credit_purchases")
    }
    with engine.connect() as conn:
        version = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert version == ScriptDirectory.from_config(config).get_current_head()
