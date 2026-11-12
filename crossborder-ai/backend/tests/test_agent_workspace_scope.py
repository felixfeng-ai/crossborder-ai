"""Agent 工作区对话隔离。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.conversation import Conversation
from app.models.user import User


@pytest.mark.asyncio
async def test_conversation_list_filters_by_workspace(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    db_session.add_all([
        Conversation(user_id=user.id, title="通用对话", workspace="general"),
        Conversation(user_id=user.id, title="营销对话", workspace="marketing"),
    ])
    await db_session.flush()

    response = await client.get(
        "/api/v1/agent/conversations",
        params={"workspace": "marketing"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["营销对话"]


@pytest.mark.asyncio
async def test_create_conversation_persists_workspace(
    client,
    auth_headers,
    db_session,
):
    response = await client.post(
        "/api/v1/agent/conversations",
        params={"workspace": "marketing"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    conversation = await db_session.get(
        Conversation,
        uuid.UUID(response.json()["id"]),
    )
    assert conversation is not None
    assert conversation.workspace == "marketing"
