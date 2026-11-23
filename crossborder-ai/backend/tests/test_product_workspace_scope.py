"""商品工作区隔离行为测试。"""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select

from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
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
        name="运营团队",
        slug=f"team-{uuid4().hex[:12]}",
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


def _product_scope_headers(headers: dict[str, str], workspace: Workspace):
    return {**headers, "X-Workspace-Id": str(workspace.id)}


@pytest.mark.asyncio
async def test_legacy_web_create_defaults_to_personal_workspace(
    client,
    db_session,
):
    headers, user, personal = await _register(
        client,
        db_session,
        "product-workspace-personal@example.com",
    )

    response = await client.post(
        "/api/v1/products/manual",
        headers=headers,
        json={
            "title": "Workspace scoped product",
            "url": "https://example.com/products/one",
            "sku": "SKU-ONE",
            "stock_quantity": 5,
        },
    )

    assert response.status_code == 201
    product = (
        await db_session.execute(
            select(Product).where(
                Product.id == UUID(response.json()["product"]["id"])
            )
        )
    ).scalar_one()
    assert product.workspace_id == personal.id
    assert product.created_by_user_id == user.id


@pytest.mark.asyncio
async def test_team_workspace_does_not_mix_personal_products(
    client,
    db_session,
):
    headers, user, personal = await _register(
        client,
        db_session,
        "product-workspace-switch@example.com",
    )
    team = await _create_team_workspace(db_session, user)

    personal_create = await client.post(
        "/api/v1/products/manual",
        headers=headers,
        json={
            "title": "Personal product",
            "url": "https://example.com/products/personal",
        },
    )
    team_create = await client.post(
        "/api/v1/products/manual",
        headers=_product_scope_headers(headers, team),
        json={
            "title": "Team product",
            "url": "https://example.com/products/team",
        },
    )

    personal_list = await client.get("/api/v1/products", headers=headers)
    team_list = await client.get(
        "/api/v1/products",
        headers=_product_scope_headers(headers, team),
    )

    assert personal_create.status_code == 201
    assert team_create.status_code == 201
    assert [
        item["title"] for item in personal_list.json()["items"]
    ] == ["Personal product"]
    assert [
        item["title"] for item in team_list.json()["items"]
    ] == ["Team product"]

    team_product_id = team_create.json()["product"]["id"]
    wrong_scope = await client.get(
        f"/api/v1/products/{team_product_id}",
        headers=headers,
    )
    assert wrong_scope.status_code == 404

    saved_team_product = (
        await db_session.execute(
            select(Product).where(Product.id == UUID(team_product_id))
        )
    ).scalar_one()
    assert saved_team_product.workspace_id == team.id
    assert saved_team_product.created_by_user_id == user.id
    assert saved_team_product.workspace_id != personal.id


@pytest.mark.asyncio
async def test_non_member_workspace_request_is_hidden(client, db_session):
    owner_headers, owner, _personal = await _register(
        client,
        db_session,
        "product-workspace-owner@example.com",
    )
    outsider_headers, _outsider, _outsider_personal = await _register(
        client,
        db_session,
        "product-workspace-outsider@example.com",
    )
    team = await _create_team_workspace(db_session, owner)

    response = await client.get(
        "/api/v1/products",
        headers=_product_scope_headers(outsider_headers, team),
    )

    assert response.status_code == 404
    assert owner_headers["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_product_variants_follow_product_workspace(client, db_session):
    headers, user, _personal = await _register(
        client,
        db_session,
        "product-variant-workspace@example.com",
    )
    team = await _create_team_workspace(db_session, user)
    team_headers = _product_scope_headers(headers, team)
    product_response = await client.post(
        "/api/v1/products/manual",
        headers=team_headers,
        json={
            "title": "Team variant product",
            "url": "https://example.com/products/team-variant",
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["product"]["id"]

    create_variant = await client.post(
        f"/api/v1/products/{product_id}/variants",
        headers=team_headers,
        json={"sku": "TEAM-VARIANT", "stock_quantity": 8},
    )
    team_variants = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=team_headers,
    )
    wrong_scope = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=headers,
    )

    assert create_variant.status_code == 201
    assert team_variants.status_code == 200
    assert team_variants.json()["items"][0]["sku"] == "TEAM-VARIANT"
    assert wrong_scope.status_code == 404

    variant = (
        await db_session.execute(
            select(ProductVariant).where(
                ProductVariant.id == UUID(create_variant.json()["id"])
            )
        )
    ).scalar_one()
    assert variant.workspace_id == team.id
    assert variant.created_by_user_id == user.id


def test_product_workspace_migration_adds_scope_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "product-workspace-scope.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    for table_name in ("products", "product_variants"):
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
async def test_product_workspace_backfill_is_idempotent_and_reports_unresolved(
    db_session,
):
    from app.services.workspace_backfill import backfill_workspace_scope

    user = User(
        email="product-backfill@example.com",
        username="product-backfill",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    personal = await ensure_personal_workspace(db_session, user)

    product = Product(
        user_id=user.id,
        url="https://example.com/products/backfill",
        title="Backfill me",
    )
    db_session.add(product)
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="BACKFILL-SKU",
    )
    unresolved = Product(
        user_id=None,
        url="https://example.com/products/unresolved",
        title="No owner",
    )
    db_session.add_all([variant, unresolved])
    await db_session.commit()

    first = await backfill_workspace_scope(
        db_session,
        batch_size=1,
    )
    await db_session.refresh(product)
    await db_session.refresh(variant)

    assert product.workspace_id == personal.id
    assert product.created_by_user_id == user.id
    assert variant.workspace_id == personal.id
    assert variant.created_by_user_id == user.id
    assert first["products"]["updated"] == 1
    assert first["product_variants"]["updated"] == 1
    assert first["products"]["unresolved"] == 1

    second = await backfill_workspace_scope(
        db_session,
        batch_size=1,
    )
    assert second["products"]["updated"] == 0
    assert second["product_variants"]["updated"] == 0
    assert second["products"]["unresolved"] == 1
