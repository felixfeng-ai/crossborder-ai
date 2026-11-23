"""Persona 品牌资料的工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.persona import Persona
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
        name="Persona Team",
        slug="persona-team",
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
async def test_persona_get_is_scoped_to_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    db_session.add_all(
        [
            Persona(
                user_id=user.id,
                workspace_id=personal.id,
                brand_name="Personal Brand",
            ),
            Persona(
                user_id=user.id,
                workspace_id=team.id,
                brand_name="Team Brand",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/settings/persona",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 200
    assert response.json()["brand_name"] == "Team Brand"


@pytest.mark.asyncio
async def test_persona_update_does_not_overwrite_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    personal_persona = Persona(
        user_id=user.id,
        workspace_id=personal.id,
        brand_name="Personal Brand",
    )
    db_session.add(personal_persona)
    await db_session.commit()

    response = await client.put(
        "/api/v1/settings/persona",
        json={"brand_name": "Team Brand"},
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 200
    await db_session.refresh(personal_persona)
    team_persona = (
        await db_session.execute(
            select(Persona).where(Persona.workspace_id == team.id)
        )
    ).scalar_one()
    assert personal_persona.brand_name == "Personal Brand"
    assert team_persona.brand_name == "Team Brand"
