"""工作区套餐生命周期行为测试。"""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from app.dependencies import require_admin
from app.main import app
from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.workspace_billing import (
    activate_workspace_plan,
    get_active_workspace_subscription,
    get_or_create_workspace_wallet,
    get_workspace_current_plan,
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
    await ensure_personal_workspace(db_session, user)
    return (
        {"Authorization": f"Bearer {response.json()['access_token']}"},
        user,
    )


async def _team_workspace(db_session, user: User) -> Workspace:
    workspace = Workspace(
        name="Subscription Team",
        slug=f"subscription-team-{uuid4().hex[:12]}",
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
async def test_team_plan_upgrade_creates_workspace_subscription(
    client,
    db_session,
):
    headers, user = await _register(
        client,
        db_session,
        "workspace-subscription@example.com",
    )
    team = await _team_workspace(db_session, user)
    team_headers = _headers_for(headers, team)
    admin = User(
        email="workspace-subscription-admin@example.com",
        username="workspace-subscription-admin",
        password_hash="not-used",
    )
    db_session.add(admin)
    await db_session.commit()
    app.dependency_overrides[require_admin] = lambda: admin

    try:
        submitted = await client.post(
            "/api/v1/billing/upgrade",
            headers=team_headers,
            json={
                "plan": "standard",
                "contact": "team-plan-wx",
                "billing_cycle": "monthly",
            },
        )
        assert submitted.status_code == 200, submitted.text
        request_id = submitted.json()["id"]
        upgrade_request = await db_session.get(
            PlanUpgradeRequest,
            UUID(request_id),
        )
        assert upgrade_request.workspace_id == team.id
        assert upgrade_request.created_by_user_id == user.id

        approved = await client.post(
            f"/api/v1/billing/upgrades/{request_id}/approve",
            headers={"Authorization": "Bearer admin"},
            json={"note": "团队套餐到账"},
        )
        assert approved.status_code == 200, approved.text
    finally:
        app.dependency_overrides.pop(require_admin, None)

    subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == team.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalar_one()
    wallet = await get_or_create_workspace_wallet(db_session, team)
    await db_session.refresh(wallet)
    await db_session.refresh(user)

    assert subscription.plan == "standard"
    assert subscription.payer_user_id == user.id
    assert (subscription.expires_at - subscription.starts_at).days == 30
    assert wallet.plan_credits == 800
    assert workspace_wallet_total(wallet) == 800
    assert user.plan == "free"

    wallet_response = await client.get(
        "/api/v1/billing/wallet",
        headers=team_headers,
    )
    assert wallet_response.status_code == 200
    assert wallet_response.json()["plan"] == "standard"
    assert wallet_response.json()["plan_expires_at"]

    duplicate = await client.post(
        "/api/v1/billing/upgrade",
        headers=team_headers,
        json={
            "plan": "standard",
            "contact": "team-plan-wx",
            "billing_cycle": "monthly",
        },
    )
    assert duplicate.status_code == 409
    professional = await client.post(
        "/api/v1/billing/upgrade",
        headers=team_headers,
        json={
            "plan": "professional",
            "contact": "team-plan-wx",
            "billing_cycle": "monthly",
        },
    )
    assert professional.status_code == 200


@pytest.mark.asyncio
async def test_personal_plan_request_remains_user_scoped(
    client,
    db_session,
):
    headers, user = await _register(
        client,
        db_session,
        "workspace-subscription-personal@example.com",
    )
    submitted = await client.post(
        "/api/v1/billing/upgrade",
        headers=headers,
        json={
            "plan": "standard",
            "contact": "personal-plan-wx",
            "billing_cycle": "monthly",
        },
    )

    assert submitted.status_code == 200, submitted.text
    upgrade_request = await db_session.get(
        PlanUpgradeRequest,
        UUID(submitted.json()["id"]),
    )
    assert upgrade_request.workspace_id is not None
    assert upgrade_request.created_by_user_id == user.id


def test_workspace_subscription_migration_adds_request_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workspace-subscription.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "head")
    columns = {
        column["name"]
        for column in sa.inspect(engine).get_columns(
            "plan_upgrade_requests"
        )
    }

    assert {"workspace_id", "created_by_user_id"} <= columns
    with engine.connect() as conn:
        version = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert version == ScriptDirectory.from_config(config).get_current_head()


@pytest.mark.asyncio
async def test_workspace_plan_activation_replaces_previous_subscription(
    db_session,
):
    user = User(
        email="workspace-plan-activation@example.com",
        username="workspace-plan-activation",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    team = await _team_workspace(db_session, user)

    first = await activate_workspace_plan(
        db_session,
        workspace=team,
        plan="standard",
        payer_user_id=user.id,
    )
    second = await activate_workspace_plan(
        db_session,
        workspace=team,
        plan="professional",
        payer_user_id=user.id,
    )
    await db_session.refresh(first)
    active = await get_active_workspace_subscription(
        db_session,
        team.id,
    )
    wallet = await get_or_create_workspace_wallet(db_session, team)
    await db_session.refresh(wallet)

    assert first.status == "replaced"
    assert second.status == "active"
    assert active is not None
    assert active.id == second.id
    assert await get_workspace_current_plan(db_session, team.id) == "professional"
    assert wallet.plan_credits == 3000

    with pytest.raises(ValueError, match="无效的付费套餐"):
        await activate_workspace_plan(
            db_session,
            workspace=team,
            plan="free",
            payer_user_id=user.id,
        )
