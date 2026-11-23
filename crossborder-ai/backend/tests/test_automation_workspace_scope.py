"""自动化偏好与执行状态的工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspaces import ensure_personal_workspace


async def _workspace_pair(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    personal = await ensure_personal_workspace(db_session, user)
    team = Workspace(
        name="Automation Team",
        slug="automation-team",
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
    await db_session.commit()
    return user, personal, team


@pytest.mark.asyncio
async def test_automation_settings_are_saved_per_workspace(
    client,
    auth_headers,
    db_session,
):
    _user, personal, team = await _workspace_pair(db_session)
    team_headers = {
        **auth_headers,
        "X-Workspace-Id": str(team.id),
    }

    updated = await client.put(
        "/api/v1/settings/automation",
        json={"daily_store_check": False},
        headers=team_headers,
    )
    personal_settings = await client.get(
        "/api/v1/settings/automation",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert updated.status_code == 200
    team_task = next(
        item
        for item in updated.json()["tasks"]
        if item["key"] == "store_check"
    )
    personal_task = next(
        item
        for item in personal_settings.json()["tasks"]
        if item["key"] == "store_check"
    )
    assert team_task["enabled"] is False
    assert personal_task["enabled"] is True
