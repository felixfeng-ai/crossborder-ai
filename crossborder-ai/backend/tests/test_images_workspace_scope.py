"""图片任务与素材的跨工作区隔离测试。"""

import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspaces import ensure_personal_workspace


async def _workspace_pair(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    personal = await ensure_personal_workspace(db_session, user)
    team = Workspace(
        name="Scope Team",
        slug="scope-team",
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


@pytest.mark.asyncio
async def test_image_status_rejects_task_from_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    user.plan = "professional"
    task = ImageGenerationTask(
        user_id=user.id,
        workspace_id=team.id,
        prompt="team only",
        status="pending",
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/images/status/{task.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_image_status_allows_explicit_owning_workspace(
    client,
    auth_headers,
    db_session,
):
    user, _personal, team = await _workspace_pair(db_session)
    task = ImageGenerationTask(
        user_id=user.id,
        workspace_id=team.id,
        prompt="team task",
        status="pending",
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/images/status/{task.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == str(task.id)


@pytest.mark.asyncio
async def test_image_history_is_scoped_to_requested_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    db_session.add_all(
        [
            ImageGenerationTask(
                user_id=user.id,
                workspace_id=personal.id,
                prompt="personal task",
                status="completed",
                image_urls="[]",
            ),
            ImageGenerationTask(
                user_id=user.id,
                workspace_id=team.id,
                prompt="team task",
                status="completed",
                image_urls="[]",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/images/history",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 200
    assert [item["prompt"] for item in response.json()] == ["personal task"]


@pytest.mark.asyncio
async def test_image_asset_list_hides_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    common = {
        "user_id": user.id,
        "kind": "upload",
        "content_type": "image/webp",
        "width": 10,
        "height": 10,
        "file_size": 10,
    }
    db_session.add_all(
        [
            ImageAsset(
                workspace_id=personal.id,
                name="personal asset",
                storage_key="personal.webp",
                **common,
            ),
            ImageAsset(
                workspace_id=team.id,
                name="team asset",
                storage_key="team.webp",
                **common,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/images/assets",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == [
        "personal asset"
    ]


@pytest.mark.asyncio
async def test_image_asset_process_rejects_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=team.id,
        name="team asset",
        kind="upload",
        storage_key="team.webp",
        content_type="image/webp",
        width=10,
        height=10,
        file_size=10,
    )
    db_session.add(asset)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/images/assets/{asset.id}/process",
        json={"preset_id": "amazon_main"},
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_image_edit_rejects_source_from_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    user.plan = "professional"
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=team.id,
        name="team source",
        kind="upload",
        storage_key="team-source.webp",
        content_type="image/webp",
        width=10,
        height=10,
        file_size=10,
    )
    db_session.add(asset)
    await db_session.commit()

    response = await client.post(
        "/api/v1/images/edit",
        json={
            "source_asset_id": str(asset.id),
            "operation": "upscale",
            "scale": 2,
        },
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_image_upload_records_explicit_workspace(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    _user, _personal, team = await _workspace_pair(db_session)
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(image, format="PNG")

    response = await client.post(
        "/api/v1/images/assets/upload",
        files={"file": ("team.png", image.getvalue(), "image/png")},
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 201
    asset = await db_session.get(
        ImageAsset,
        uuid.UUID(response.json()["id"]),
    )
    assert asset is not None
    assert asset.workspace_id == team.id
