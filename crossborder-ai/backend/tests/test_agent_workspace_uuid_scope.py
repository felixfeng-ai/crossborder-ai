"""Agent 对话与任务的 UUID 工作区隔离测试。"""

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.agent_task import AgentTask
from app.models.conversation import Conversation, ConversationMessage
from app.models.listing_draft import ListingDraft
from app.models.operation_alert import OperationAlert
from app.models.product import Product
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services import agent_task_executor
from app.services.workspaces import ensure_personal_workspace


async def _workspace_pair(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    personal = await ensure_personal_workspace(db_session, user)
    team = Workspace(
        name="Agent Team",
        slug="agent-team",
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
async def test_agent_conversation_list_is_scoped_by_workspace_id(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    db_session.add_all(
        [
            Conversation(
                user_id=user.id,
                workspace_id=personal.id,
                title="personal conversation",
                workspace="general",
            ),
            Conversation(
                user_id=user.id,
                workspace_id=team.id,
                title="team conversation",
                workspace="general",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/agent/conversations",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == [
        "team conversation"
    ]


@pytest.mark.asyncio
async def test_agent_task_rejects_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    task = AgentTask(
        user_id=user.id,
        workspace_id=team.id,
        task_type="agent_run",
        status="pending",
        input="{}",
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/agent/tasks/{task.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_idempotency_key_is_scoped_by_workspace(
    client,
    auth_headers,
    db_session,
):
    user, _personal, team = await _workspace_pair(db_session)
    user.plan = "standard"
    user.credits = 10
    await db_session.commit()
    common_headers = {
        **auth_headers,
        "Idempotency-Key": "shared-agent-key",
    }

    personal_response = await client.post(
        "/api/v1/agent/run",
        json={"instruction": "检查今天的工作"},
        headers=common_headers,
    )
    team_response = await client.post(
        "/api/v1/agent/run",
        json={"instruction": "检查今天的工作"},
        headers={
            **common_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert personal_response.status_code == 202
    assert team_response.status_code == 202
    assert personal_response.json()["task_id"] != team_response.json()["task_id"]


@pytest.mark.asyncio
async def test_agent_listing_tool_rejects_other_workspace(
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    product = Product(
        user_id=user.id,
        workspace_id=team.id,
        created_by_user_id=user.id,
        title="Team product",
        url="https://example.com/team-agent-product",
    )
    db_session.add(product)
    await db_session.flush()
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=team.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="amazon",
        language="en",
        tone="professional",
        status="ready",
        title="Team listing",
        version=1,
        content_hash="hash",
        compliance_status="pass",
    )
    db_session.add(listing)
    await db_session.flush()
    orchestrator = AgentOrchestrator(
        user=user,
        db=db_session,
        workspace_id=personal.id,
    )

    result = await orchestrator._do_get_listing(
        {"listing_id": str(listing.id)}
    )

    assert result["status"] == "failed"
    assert result["error"] == "Listing 不存在"


@pytest.mark.asyncio
async def test_agent_create_product_records_conversation_workspace(
    auth_headers,
    db_session,
):
    user, _personal, team = await _workspace_pair(db_session)
    orchestrator = AgentOrchestrator(
        user=user,
        db=db_session,
        workspace_id=team.id,
    )

    result = await orchestrator._do_create_product(
        {
            "url": "https://example.com/team-created-product",
            "title": "Team created product",
        }
    )

    assert result["status"] == "success"
    product = await db_session.get(
        Product,
        uuid.UUID(result["product_id"]),
    )
    assert product is not None
    assert product.workspace_id == team.id
    assert product.created_by_user_id == user.id


@pytest.mark.asyncio
async def test_agent_operations_tools_are_scoped_to_conversation_workspace(
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    personal_product = Product(
        user_id=user.id,
        workspace_id=personal.id,
        title="Personal product",
        url="https://example.com/personal-agent-product",
    )
    team_product = Product(
        user_id=user.id,
        workspace_id=team.id,
        title="Team product",
        url="https://example.com/team-agent-product",
    )
    db_session.add_all([personal_product, team_product])
    await db_session.flush()
    db_session.add_all(
        [
            OperationAlert(
                user_id=user.id,
                workspace_id=personal.id,
                product_id=personal_product.id,
                alert_type="low_stock",
                severity="warning",
                title="Personal stock",
                message="personal alert",
                status="open",
            ),
            OperationAlert(
                user_id=user.id,
                workspace_id=team.id,
                product_id=team_product.id,
                alert_type="out_of_stock",
                severity="critical",
                title="Team stock",
                message="team alert",
                status="open",
            ),
        ]
    )
    await db_session.flush()
    orchestrator = AgentOrchestrator(
        user=user,
        db=db_session,
        workspace_id=personal.id,
    )

    digest = await orchestrator._do_get_operations_digest({})
    store_check = await orchestrator._do_store_check({})

    assert digest["data"]["total"] == 1
    assert digest["data"]["priority_items"][0]["title"] == "Personal stock"
    assert store_check["data"]["total"] == 1


@pytest.mark.asyncio
async def test_agent_task_does_not_append_to_other_workspace_conversation(
    auth_headers,
    db_session,
    monkeypatch,
):
    user, personal, team = await _workspace_pair(db_session)
    user.plan = "standard"
    user.credits = 10
    team_conversation = Conversation(
        user_id=user.id,
        workspace_id=team.id,
        title="team conversation",
        workspace="general",
    )
    db_session.add(team_conversation)
    await db_session.flush()
    task = AgentTask(
        user_id=user.id,
        workspace_id=personal.id,
        task_type="agent_run",
        status="running",
        input=json.dumps(
            {
                "instruction": "summarize today's work",
                "conversation_id": str(team_conversation.id),
            }
        ),
    )
    db_session.add(task)
    await db_session.commit()
    factory = async_sessionmaker(
        db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        agent_task_executor,
        "async_session_factory",
        factory,
    )

    async def fake_run(self, instruction, history=None, max_rounds=8):
        return {
            "status": "success",
            "summary": "work summary",
            "steps": [],
        }

    monkeypatch.setattr(AgentOrchestrator, "run", fake_run)
    await agent_task_executor.execute_agent_task(task.id)

    messages = (
        await db_session.execute(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == team_conversation.id
            )
        )
    ).scalars().all()
    assert messages == []
