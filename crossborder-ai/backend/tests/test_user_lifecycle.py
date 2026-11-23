"""用户注销与工作区数据生命周期测试。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.models.image_generation_task import ImageGenerationTask
from app.models.listing_draft import ListingDraft
from app.models.marketing_campaign import MarketingCampaign
from app.models.notification import MobileDevice
from app.models.persona import Persona
from app.models.product import Product
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.models.workspace import Workspace, WorkspaceMember
from app.services.user_lifecycle import (
    WorkspaceLifecycleError,
    delete_user_account,
    purge_expired_workspaces,
    purge_workspace,
    restore_workspace,
    run_user_lifecycle_drill,
)
from app.services.workspaces import ensure_personal_workspace


def test_workspace_business_models_separate_actor_and_owner_fks():
    workspace_models = (
        (Product, "user_id"),
        (ListingDraft, "user_id"),
        (ImageGenerationTask, "user_id"),
        (VideoGenerationTask, "user_id"),
        (MarketingCampaign, "user_id"),
        (Persona, "user_id"),
    )
    for model, actor_field in workspace_models:
        actor_foreign_key = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if list(constraint.columns)[0].name == actor_field
        )
        workspace_foreign_key = next(
            constraint
            for constraint in model.__table__.foreign_key_constraints
            if list(constraint.columns)[0].name == "workspace_id"
        )
        assert actor_foreign_key.ondelete == "SET NULL"
        assert workspace_foreign_key.ondelete == "CASCADE"


@pytest.mark.asyncio
async def test_user_deletion_anonymizes_user_and_archives_personal_workspace(
    db_session,
):
    user = User(
        email="delete-personal@example.com",
        username="delete-personal",
        password_hash="original-password-hash",
        plan="standard",
        credits=120,
    )
    db_session.add(user)
    await db_session.flush()
    personal = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=personal.id,
        created_by_user_id=user.id,
        title="注销后仍保留的商品",
        url="https://example.com/delete-personal-product",
    )
    device = MobileDevice(
        user_id=user.id,
        expo_push_token="ExponentPushToken[lifecycle-test]",
        platform="ios",
        device_name="Lifecycle Test iPhone",
    )
    db_session.add_all([product, device])
    await db_session.commit()
    device_id = device.id
    product_id = product.id
    workspace_id = personal.id

    before = datetime.now(timezone.utc)
    result = await delete_user_account(
        db_session,
        user_id=user.id,
        reason="user_requested",
        now=before,
    )
    await db_session.commit()
    db_session.expire_all()
    await db_session.refresh(user)

    preserved_product = (
        await db_session.execute(
            select(Product).where(Product.id == product_id)
        )
    ).scalar_one()
    archived_workspace = await db_session.get(Workspace, workspace_id)

    assert result["user_deleted"] is True
    assert result["archived_workspace_ids"] == [str(workspace_id)]
    assert user.deleted_at is not None
    assert user.email != "delete-personal@example.com"
    assert user.username is None
    assert user.password_hash != "original-password-hash"
    assert archived_workspace.status == "archived"
    assert archived_workspace.owner_user_id is None
    assert archived_workspace.purge_after is not None
    assert preserved_product.workspace_id == workspace_id
    assert preserved_product.user_id is None
    assert await db_session.get(MobileDevice, device_id) is None


@pytest.mark.asyncio
async def test_owned_team_workspace_transfers_to_active_admin(db_session):
    owner = User(
        email="delete-team-owner@example.com",
        username="delete-team-owner",
        password_hash="not-used",
        plan="standard",
    )
    successor = User(
        email="delete-team-successor@example.com",
        username="delete-team-successor",
        password_hash="not-used",
        plan="free",
    )
    db_session.add_all([owner, successor])
    await db_session.flush()
    team = Workspace(
        name="保留的团队工作区",
        slug="delete-team-workspace",
        type="team",
        owner_user_id=owner.id,
        status="active",
    )
    db_session.add(team)
    await db_session.flush()
    owner_membership = WorkspaceMember(
        workspace_id=team.id,
        user_id=owner.id,
        role="owner",
        status="active",
    )
    successor_membership = WorkspaceMember(
        workspace_id=team.id,
        user_id=successor.id,
        role="admin",
        status="active",
    )
    product = Product(
        user_id=owner.id,
        workspace_id=team.id,
        created_by_user_id=owner.id,
        title="团队商品",
        url="https://example.com/team-product",
    )
    db_session.add_all(
        [owner_membership, successor_membership, product]
    )
    await db_session.commit()

    result = await delete_user_account(
        db_session,
        user_id=owner.id,
    )
    await db_session.commit()

    await db_session.refresh(team)
    await db_session.refresh(owner_membership)
    await db_session.refresh(successor_membership)
    await db_session.refresh(product)

    assert result["archived_workspace_ids"] == []
    assert result["transferred_workspace_ids"] == [str(team.id)]
    assert team.status == "active"
    assert team.owner_user_id == successor.id
    assert owner_membership.status == "removed"
    assert successor_membership.role == "owner"
    assert successor_membership.status == "active"
    assert product.workspace_id == team.id
    assert product.user_id is None


@pytest.mark.asyncio
async def test_owned_team_workspace_without_successor_is_archived(db_session):
    owner = User(
        email="delete-solo-owner@example.com",
        username="delete-solo-owner",
        password_hash="not-used",
        plan="professional",
    )
    db_session.add(owner)
    await db_session.flush()
    team = Workspace(
        name="无人接手的团队",
        slug="delete-solo-team",
        type="team",
        owner_user_id=owner.id,
        status="active",
    )
    db_session.add(team)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=team.id,
            user_id=owner.id,
            role="owner",
            status="active",
        )
    )
    product = Product(
        user_id=owner.id,
        workspace_id=team.id,
        created_by_user_id=owner.id,
        title="无人接手但保留的商品",
        url="https://example.com/orphaned-team-product",
    )
    db_session.add(product)
    await db_session.commit()

    result = await delete_user_account(db_session, user_id=owner.id)
    await db_session.commit()

    await db_session.refresh(team)
    await db_session.refresh(product)

    assert result["transferred_workspace_ids"] == []
    assert result["archived_workspace_ids"] == [str(team.id)]
    assert team.status == "archived"
    assert team.owner_user_id is None
    assert team.archived_at is not None
    assert team.purge_after is not None
    assert product.workspace_id == team.id
    assert product.user_id is None


@pytest.mark.asyncio
async def test_team_member_deletion_detaches_their_records_only(db_session):
    owner = User(
        email="member-delete-owner@example.com",
        username="member-delete-owner",
        password_hash="not-used",
    )
    member = User(
        email="member-delete-user@example.com",
        username="member-delete-user",
        password_hash="not-used",
    )
    db_session.add_all([owner, member])
    await db_session.flush()
    team = Workspace(
        name="成员注销团队",
        slug="member-delete-team",
        type="team",
        owner_user_id=owner.id,
        status="active",
    )
    db_session.add(team)
    await db_session.flush()
    db_session.add_all(
        [
            WorkspaceMember(
                workspace_id=team.id,
                user_id=owner.id,
                role="owner",
                status="active",
            ),
            WorkspaceMember(
                workspace_id=team.id,
                user_id=member.id,
                role="operator",
                status="active",
            ),
        ]
    )
    owner_product = Product(
        user_id=owner.id,
        workspace_id=team.id,
        created_by_user_id=owner.id,
        title="所有者商品",
        url="https://example.com/owner-product",
    )
    member_product = Product(
        user_id=member.id,
        workspace_id=team.id,
        created_by_user_id=member.id,
        title="成员商品",
        url="https://example.com/member-product",
    )
    db_session.add_all([owner_product, member_product])
    await db_session.commit()
    owner_id = owner.id
    member_id = member.id

    await delete_user_account(db_session, user_id=member_id)
    await db_session.commit()
    db_session.expire_all()

    await db_session.refresh(team)
    await db_session.refresh(owner_product)
    await db_session.refresh(member_product)
    assert team.status == "active"
    assert team.owner_user_id == owner_id
    assert owner_product.user_id == owner_id
    assert member_product.user_id is None
    assert member_product.created_by_user_id is None


@pytest.mark.asyncio
async def test_user_lifecycle_drill_passes_and_rolls_back(db_session):
    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    before_users = len(
        (await db_session.execute(select(User.id))).scalars().all()
    )

    result = await run_user_lifecycle_drill(db_session)
    assert result["passed"] is True, json.dumps(result, ensure_ascii=False)
    assert all(result["checks"].values())

    await db_session.rollback()
    after_users = len(
        (await db_session.execute(select(User.id))).scalars().all()
    )
    assert after_users == before_users


@pytest.mark.asyncio
async def test_archived_workspace_can_be_restored_to_new_owner(db_session):
    user = User(
        email="restore-before-purge@example.com",
        username="restore-before-purge",
        password_hash="not-used",
    )
    successor = User(
        email="restore-new-owner@example.com",
        username="restore-new-owner",
        password_hash="not-used",
    )
    db_session.add_all([user, successor])
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="恢复商品",
        url="https://example.com/restore-product",
    )
    db_session.add(product)
    await db_session.commit()
    await delete_user_account(db_session, user_id=user.id)
    await db_session.commit()

    result = await restore_workspace(
        db_session,
        workspace_id=workspace.id,
        new_owner_user_id=successor.id,
        actor_user_id=successor.id,
    )
    await db_session.commit()

    await db_session.refresh(workspace)
    await db_session.refresh(product)
    membership = (
        await db_session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == successor.id,
            )
        )
    ).scalar_one()

    assert result["restored"] is True
    assert workspace.status == "active"
    assert workspace.owner_user_id == successor.id
    assert workspace.archived_at is None
    assert workspace.purge_after is None
    assert workspace.archived_by_user_id is None
    assert membership.role == "owner"
    assert membership.status == "active"
    assert product.id is not None


@pytest.mark.asyncio
async def test_workspace_purge_requires_expired_archive(db_session):
    user = User(
        email="purge-window@example.com",
        username="purge-window",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    await db_session.commit()
    await delete_user_account(
        db_session,
        user_id=user.id,
        retention_days=30,
    )
    await db_session.commit()

    with pytest.raises(WorkspaceLifecycleError, match="尚未到清理时间"):
        await purge_workspace(
            db_session,
            workspace_id=workspace.id,
            now=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_expired_workspace_purge_deletes_workspace_owned_data(db_session):
    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    user = User(
        email="purge-expired@example.com",
        username="purge-expired",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="到期清理商品",
        url="https://example.com/purge-product",
    )
    db_session.add(product)
    await db_session.commit()
    archived_at = datetime.now(timezone.utc)
    archived = await delete_user_account(
        db_session,
        user_id=user.id,
        retention_days=1,
        now=archived_at,
    )
    await db_session.commit()
    workspace_id = workspace.id
    product_id = product.id

    result = await purge_workspace(
        db_session,
        workspace_id=workspace_id,
        now=archived_at + timedelta(days=2),
    )
    await db_session.commit()

    assert archived["archived_workspace_ids"] == [str(workspace_id)]
    assert result["purged"] is True
    db_session.expire_all()
    assert await db_session.get(Workspace, workspace_id) is None
    assert await db_session.get(Product, product_id) is None


@pytest.mark.asyncio
async def test_delete_account_api_requires_confirmation_and_invalidates_token(
    client,
    db_session,
):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "delete-account-api@example.com",
            "username": "delete-account-api",
            "password": "testpass123",
        },
    )
    assert registered.status_code == 201
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}"
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "delete-account-api@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="API 注销保留商品",
        url="https://example.com/api-delete-product",
    )
    device = MobileDevice(
        user_id=user.id,
        expo_push_token="ExponentPushToken[api-lifecycle-test]",
        platform="ios",
        device_name="API Lifecycle iPhone",
    )
    db_session.add_all([product, device])
    await db_session.commit()
    device_id = device.id
    product_id = product.id
    workspace_id = workspace.id

    wrong_confirmation = await client.post(
        "/api/v1/auth/delete-account",
        headers=headers,
        json={
            "password": "testpass123",
            "confirmation": "继续使用",
        },
    )
    wrong_password = await client.post(
        "/api/v1/auth/delete-account",
        headers=headers,
        json={
            "password": "wrong-password",
            "confirmation": "注销账号",
        },
    )
    deleted = await client.post(
        "/api/v1/auth/delete-account",
        headers=headers,
        json={
            "password": "testpass123",
            "confirmation": "注销账号",
        },
    )
    after_delete = await client.get("/api/v1/auth/me", headers=headers)
    old_email_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "delete-account-api@example.com",
            "password": "testpass123",
        },
    )

    preserved = (
        await db_session.execute(
            select(Product).where(Product.id == product_id)
        )
    ).scalar_one()
    preserved_workspace_id = preserved.workspace_id
    db_session.expire_all()

    assert wrong_confirmation.status_code == 422
    assert wrong_password.status_code == 400
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["user_deleted"] is True
    assert after_delete.status_code == 401
    assert old_email_login.status_code == 401
    assert preserved_workspace_id == workspace_id
    assert await db_session.get(MobileDevice, device_id) is None


@pytest.mark.asyncio
async def test_expired_workspace_cleanup_only_purges_due_workspaces(db_session):
    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    first_user = User(
        email="cleanup-due@example.com",
        username="cleanup-due",
        password_hash="not-used",
    )
    second_user = User(
        email="cleanup-future@example.com",
        username="cleanup-future",
        password_hash="not-used",
    )
    db_session.add_all([first_user, second_user])
    await db_session.flush()
    due_workspace = await ensure_personal_workspace(db_session, first_user)
    future_workspace = await ensure_personal_workspace(db_session, second_user)
    current = datetime.now(timezone.utc)
    due_workspace.status = "archived"
    due_workspace.owner_user_id = None
    due_workspace.archived_at = current - timedelta(days=40)
    due_workspace.purge_after = current - timedelta(days=1)
    future_workspace.status = "archived"
    future_workspace.owner_user_id = None
    future_workspace.archived_at = current
    future_workspace.purge_after = current + timedelta(days=10)
    db_session.add_all(
        [
            Product(
                user_id=None,
                workspace_id=due_workspace.id,
                title="到期工作区商品",
                url="https://example.com/due-cleanup-product",
            ),
            Product(
                user_id=None,
                workspace_id=future_workspace.id,
                title="保留中工作区商品",
                url="https://example.com/future-cleanup-product",
            ),
        ]
    )
    await db_session.commit()
    due_workspace_id = due_workspace.id
    future_workspace_id = future_workspace.id

    result = await purge_expired_workspaces(
        db_session,
        now=current,
    )
    await db_session.commit()
    db_session.expire_all()

    assert result["purged_workspace_ids"] == [str(due_workspace_id)]
    assert await db_session.get(Workspace, due_workspace_id) is None
    assert await db_session.get(Workspace, future_workspace_id) is not None


@pytest.mark.asyncio
async def test_user_deletion_preserves_multiple_workspace_business_families(
    db_session,
):
    user = User(
        email="delete-business-family@example.com",
        username="delete-business-family",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="业务族商品",
        url="https://example.com/business-family-product",
    )
    db_session.add(product)
    await db_session.flush()
    draft = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="amazon",
        title="Listing 草稿",
        content_hash="business-family-hash",
    )
    image_task = ImageGenerationTask(
        user_id=user.id,
        workspace_id=workspace.id,
        prompt="生成商品图",
    )
    video_task = VideoGenerationTask(
        user_id=user.id,
        workspace_id=workspace.id,
        model="preview-video",
        resolution="720p",
        duration=5,
        prompt="生成商品视频",
    )
    campaign = MarketingCampaign(
        user_id=user.id,
        workspace_id=workspace.id,
        title="保留的营销活动",
    )
    persona = Persona(
        user_id=user.id,
        workspace_id=workspace.id,
        brand_name="保留品牌",
    )
    db_session.add_all(
        [draft, image_task, video_task, campaign, persona]
    )
    await db_session.commit()
    draft_id = draft.id
    image_task_id = image_task.id
    video_task_id = video_task.id
    campaign_id = campaign.id
    persona_id = persona.id

    await delete_user_account(db_session, user_id=user.id)
    await db_session.commit()
    db_session.expire_all()

    assert (await db_session.get(ListingDraft, draft_id)).user_id is None
    assert (
        await db_session.get(ImageGenerationTask, image_task_id)
    ).user_id is None
    assert (
        await db_session.get(VideoGenerationTask, video_task_id)
    ).user_id is None
    assert (
        await db_session.get(MarketingCampaign, campaign_id)
    ).user_id is None
    assert (await db_session.get(Persona, persona_id)).user_id is None
