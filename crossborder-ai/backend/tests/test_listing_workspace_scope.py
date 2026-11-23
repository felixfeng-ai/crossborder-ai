"""Listing 工作区隔离行为测试。"""

import uuid
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from app.models.listing import Listing, ListingPlatform, ListingStatus
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.ai.deepseek import DeepSeekService
from tests.ai_mock_helpers import mock_listing_ai
from app.services.workspace_billing import get_or_create_workspace_wallet
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
    token = response.json()["access_token"]
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    personal = (
        await db_session.execute(
            select(Workspace).where(
                Workspace.owner_user_id == user.id,
                Workspace.type == "personal",
            )
        )
    ).scalar_one()
    return {"Authorization": f"Bearer {token}"}, user, personal


async def _create_team_workspace(db_session, user: User) -> Workspace:
    workspace = Workspace(
        name="Listing 团队",
        slug=f"listing-team-{uuid.uuid4().hex[:12]}",
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


def _mock_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_listing_ai(
        monkeypatch,
        "Premium wireless earbuds with long battery life.",
    )


@pytest.mark.asyncio
async def test_team_listing_is_hidden_from_personal_workspace(
    client,
    db_session,
    monkeypatch,
):
    _mock_generate(monkeypatch)
    headers, user, _personal = await _register(
        client,
        db_session,
        "listing-workspace@example.com",
    )
    team = await _create_team_workspace(db_session, user)
    team_headers = _headers_for(headers, team)
    team_wallet = await get_or_create_workspace_wallet(db_session, team)
    team_wallet.plan_credits = 10
    await db_session.commit()

    product_response = await client.post(
        "/api/v1/products/manual",
        headers=team_headers,
        json={
            "title": "Team listing product",
            "url": "https://example.com/products/team-listing",
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["product"]["id"]

    generated = await client.post(
        "/api/v1/content/generate",
        headers=team_headers,
        json={
            "product_id": product_id,
            "platform": "amazon",
            "language": "en",
            "tone": "professional",
        },
    )
    assert generated.status_code == 200, generated.text
    listing_id = generated.json()["listing_id"]

    team_read = await client.get(
        f"/api/v1/listings/{listing_id}",
        headers=team_headers,
    )
    personal_read = await client.get(
        f"/api/v1/listings/{listing_id}",
        headers=headers,
    )
    personal_update = await client.put(
        f"/api/v1/listings/{listing_id}",
        headers=headers,
        json={"title": "Cross workspace edit"},
    )
    team_catalog = await client.get(
        "/api/v1/catalog/listings",
        headers=team_headers,
    )
    personal_catalog = await client.get(
        "/api/v1/catalog/listings",
        headers=headers,
    )

    assert team_read.status_code == 200
    assert personal_read.status_code == 404
    assert personal_update.status_code == 404
    assert [item["id"] for item in team_catalog.json()["items"]] == [
        listing_id
    ]
    assert personal_catalog.json()["items"] == []

    draft = (
        await db_session.execute(
            select(ListingDraft).where(ListingDraft.id == UUID(listing_id))
        )
    ).scalar_one()
    assert draft.workspace_id == team.id
    assert draft.created_by_user_id == user.id


@pytest.mark.asyncio
async def test_legacy_web_listing_generation_uses_personal_workspace(
    client,
    db_session,
    monkeypatch,
):
    _mock_generate(monkeypatch)
    headers, user, personal = await _register(
        client,
        db_session,
        "listing-workspace-personal@example.com",
    )
    product_response = await client.post(
        "/api/v1/products/manual",
        headers=headers,
        json={
            "title": "Personal listing product",
            "url": "https://example.com/products/personal-listing",
        },
    )
    product_id = product_response.json()["product"]["id"]

    generated = await client.post(
        "/api/v1/content/generate",
        headers=headers,
        json={
            "product_id": product_id,
            "platform": "amazon",
            "language": "en",
        },
    )

    assert generated.status_code == 200, generated.text
    draft = (
        await db_session.execute(
            select(ListingDraft).where(
                ListingDraft.id == UUID(generated.json()["listing_id"])
            )
        )
    ).scalar_one()
    assert draft.workspace_id == personal.id
    assert draft.created_by_user_id == user.id


def test_listing_workspace_migration_adds_scope_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "listing-workspace-scope.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    for table_name in ("listing_drafts", "listings"):
        columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        assert {"workspace_id", "created_by_user_id"} <= columns
        assert f"ix_{table_name}_workspace_id" in {
            index["name"] for index in inspector.get_indexes(table_name)
        }
    with engine.connect() as conn:
        version = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert version == ScriptDirectory.from_config(config).get_current_head()


@pytest.mark.asyncio
async def test_listing_workspace_backfill_is_idempotent(db_session):
    from app.services.workspace_backfill import backfill_workspace_scope

    user = User(
        email="listing-backfill@example.com",
        username="listing-backfill",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    personal = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=personal.id,
        created_by_user_id=user.id,
        url="https://example.com/products/listing-backfill",
        title="Listing backfill product",
    )
    db_session.add(product)
    await db_session.flush()
    draft = ListingDraft(
        user_id=user.id,
        product_id=product.id,
        platform="amazon",
        language="en",
        tone="professional",
        status="ready",
        title="Draft to backfill",
        version=1,
        content_hash="hash",
        compliance_status="pass",
    )
    legacy = Listing(
        owner_id=user.id,
        product_id=product.id,
        platform=ListingPlatform.AMAZON,
        status=ListingStatus.DRAFT,
        title="Legacy listing to backfill",
    )
    db_session.add_all([draft, legacy])
    await db_session.commit()

    first = await backfill_workspace_scope(
        db_session,
        batch_size=1,
        tables=("listing_drafts", "listings"),
    )
    await db_session.refresh(draft)
    await db_session.refresh(legacy)

    assert draft.workspace_id == personal.id
    assert draft.created_by_user_id == user.id
    assert legacy.workspace_id == personal.id
    assert legacy.created_by_user_id == user.id
    assert first["listing_drafts"]["updated"] == 1
    assert first["listings"]["updated"] == 1

    second = await backfill_workspace_scope(
        db_session,
        batch_size=1,
        tables=("listing_drafts", "listings"),
    )
    assert second["listing_drafts"]["updated"] == 0
    assert second["listings"]["updated"] == 0
