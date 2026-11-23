"""视频任务跨工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
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
        name="Video Scope Team",
        slug="video-scope-team",
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


def _task(user_id, workspace_id, prompt: str) -> VideoGenerationTask:
    return VideoGenerationTask(
        user_id=user_id,
        workspace_id=workspace_id,
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt=prompt,
        status="failed",
    )


@pytest.mark.asyncio
async def test_video_task_rejects_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    task = _task(user.id, team.id, "team video")
    db_session.add(task)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/videos/tasks/{task.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_video_history_is_scoped(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    db_session.add_all(
        [
            _task(user.id, personal.id, "personal video"),
            _task(user.id, team.id, "team video"),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/videos/history",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 200
    assert [item["prompt"] for item in response.json()] == ["team video"]
