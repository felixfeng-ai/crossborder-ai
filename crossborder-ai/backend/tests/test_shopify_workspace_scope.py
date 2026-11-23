"""Shopify 渠道列表与解绑的工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.shopify_channel import ShopifyChannel
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
        name="Shopify Team",
        slug="shopify-team",
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


def _channel(user, workspace, name: str) -> ShopifyChannel:
    return ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name=name,
        shop_domain=f"{name}.myshopify.com",
        access_token="encrypted-token",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_shopify_channel_list_and_unbind_are_workspace_scoped(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    personal_channel = _channel(user, personal, "personal-shop")
    team_channel = _channel(user, team, "team-shop")
    db_session.add_all([personal_channel, team_channel])
    await db_session.commit()
    team_headers = {
        **auth_headers,
        "X-Workspace-Id": str(team.id),
    }

    listed = await client.get(
        "/api/v1/shopify/channels",
        headers=team_headers,
    )
    hidden_delete = await client.delete(
        f"/api/v1/shopify/channels/{personal_channel.id}",
        headers=team_headers,
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(team_channel.id)]
    assert hidden_delete.status_code == 404
