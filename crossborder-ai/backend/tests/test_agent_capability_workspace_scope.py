"""Agent 能力服务的素材与生成任务工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import agent_capability_service, provider_config
from app.services.workspaces import ensure_personal_workspace


async def _workspace_pair(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    user.credits = 200
    personal = await ensure_personal_workspace(db_session, user)
    team = Workspace(
        name="Agent Capability Team",
        slug="agent-capability-team",
        type="team",
        owner_user_id=user.id,
        status="active",
    )
    db_session.add(team)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=team.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
    )
    await db_session.flush()
    return user, personal, team


def _asset(user: User, workspace: Workspace, name: str) -> ImageAsset:
    return ImageAsset(
        user_id=user.id,
        workspace_id=workspace.id,
        name=name,
        kind="upload",
        storage_key=f"{workspace.id}-{name}.png",
        content_type="image/png",
        width=800,
        height=800,
        file_size=128,
    )


@pytest.mark.asyncio
async def test_agent_image_asset_lookup_rejects_other_workspace(
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    asset = _asset(user, team, "team-only")
    db_session.add(asset)
    await db_session.flush()

    visible = await agent_capability_service.get_owned_image_asset(
        db_session,
        user.id,
        str(asset.id),
        workspace_id=team.id,
    )
    hidden = await agent_capability_service.get_owned_image_asset(
        db_session,
        user.id,
        str(asset.id),
        workspace_id=personal.id,
    )

    assert visible is not None
    assert hidden is None


@pytest.mark.asyncio
async def test_agent_image_task_records_workspace(
    auth_headers,
    db_session,
    monkeypatch,
):
    user, _personal, team = await _workspace_pair(db_session)
    asset = _asset(user, team, "team-product")
    db_session.add(asset)
    await db_session.flush()
    monkeypatch.setattr(
        provider_config,
        "get",
        lambda provider, key, default="": (
            "test-key" if provider == "aliyun" else default
        ),
    )

    task = await agent_capability_service.schedule_product_image_task(
        db_session,
        user,
        prompt="clean product hero image",
        workspace_id=team.id,
    )

    stored = await db_session.get(ImageGenerationTask, task.id)
    assert stored is not None
    assert stored.workspace_id == team.id
