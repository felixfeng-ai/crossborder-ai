"""工作区核心行为规格测试。"""

import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspaces import (
    bootstrap_personal_workspaces,
    ensure_personal_workspace,
    get_workspace_membership,
)


async def _create_user(db_session, email: str) -> User:
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used-in-this-test",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_ensure_personal_workspace_is_idempotent_and_owner_scoped(
    db_session,
):
    user = await _create_user(db_session, "workspace-owner@example.com")

    first = await ensure_personal_workspace(db_session, user)
    second = await ensure_personal_workspace(db_session, user)

    assert first.id == second.id
    assert first.type == "personal"
    assert first.owner_user_id == user.id
    assert first.status == "active"

    workspaces = (
        await db_session.execute(
            select(Workspace).where(
                Workspace.owner_user_id == user.id,
                Workspace.type == "personal",
            )
        )
    ).scalars().all()
    assert len(workspaces) == 1

    membership = (
        await db_session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == first.id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one()
    assert membership.role == "owner"
    assert membership.status == "active"


@pytest.mark.asyncio
async def test_workspace_membership_requires_active_member(db_session):
    owner = await _create_user(db_session, "workspace-owner-2@example.com")
    outsider = await _create_user(db_session, "workspace-outsider@example.com")
    workspace = await ensure_personal_workspace(db_session, owner)

    owner_membership = await get_workspace_membership(
        db_session,
        workspace_id=workspace.id,
        user_id=owner.id,
    )
    outsider_membership = await get_workspace_membership(
        db_session,
        workspace_id=workspace.id,
        user_id=outsider.id,
    )

    assert owner_membership is not None
    assert owner_membership.role == "owner"
    assert outsider_membership is None

    owner_membership.status = "disabled"
    await db_session.commit()

    disabled_membership = await get_workspace_membership(
        db_session,
        workspace_id=workspace.id,
        user_id=owner.id,
    )
    assert disabled_membership is None


@pytest.mark.asyncio
async def test_bootstrap_personal_workspaces_is_restartable(db_session):
    first_user = await _create_user(db_session, "bootstrap-1@example.com")
    second_user = await _create_user(db_session, "bootstrap-2@example.com")

    first_run = await bootstrap_personal_workspaces(db_session, batch_size=1)
    second_run = await bootstrap_personal_workspaces(db_session, batch_size=1)

    assert first_run == {"created": 2, "skipped": 0, "failed": 0}
    assert second_run == {"created": 0, "skipped": 2, "failed": 0}

    workspace_rows = (
        await db_session.execute(
            select(Workspace).where(
                Workspace.owner_user_id.in_([first_user.id, second_user.id]),
                Workspace.type == "personal",
            )
        )
    ).scalars().all()
    assert len(workspace_rows) == 2
