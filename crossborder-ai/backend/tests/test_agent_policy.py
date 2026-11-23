"""工作区 Agent 自主策略、暂停和双人审批测试。"""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.agent_policy import (
    ActionApproval,
    AgentAutonomyPolicy,
)
from app.models.agent_work import WorkItem
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.action_runtime import (
    confirm_action_run,
    get_action_definition,
    plan_action_run,
)
from app.services.agent_policy import (
    evaluate_autonomy,
    set_agent_paused,
)
from app.services.work_items import create_work_item
from app.services.workspaces import ensure_personal_workspace


async def _personal_context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    return user, workspace


async def _work_item(db_session, workspace, user, *, suffix: str):
    return await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="agent_action",
        source="agent",
        title=f"策略测试 {suffix}",
        summary="等待执行",
        status="waiting_user",
        requires_action="confirm",
    )


@pytest.mark.asyncio
async def test_policy_auto_requires_conditions_and_records_snapshot(
    db_session,
):
    user, workspace = await _personal_context(
        db_session,
        "policy-conditions@example.com",
    )
    db_session.add(
        AgentAutonomyPolicy(
            workspace_id=workspace.id,
            action_id="inventory.update",
            autonomy_level="auto",
            conditions_json=json.dumps({"max_quantity": 10}),
            enabled=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()

    denied = await evaluate_autonomy(
        db_session,
        workspace_id=workspace.id,
        definition=get_action_definition("inventory.update"),
        input_data={"stock_quantity": 11},
    )
    allowed = await evaluate_autonomy(
        db_session,
        workspace_id=workspace.id,
        definition=get_action_definition("inventory.update"),
        input_data={"stock_quantity": 8},
    )

    assert denied.autonomy_level == "confirm"
    assert "库存变更数量" in denied.reason
    assert allowed.autonomy_level == "auto"

    item = await _work_item(
        db_session,
        workspace,
        user,
        suffix="inventory",
    )
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="inventory.update",
        platform="shopify",
        target_type="inventory_item",
        target_id="item-1",
        input_data={"stock_quantity": 8},
        idempotency_key="policy-auto-inventory",
    )
    await db_session.commit()

    assert run.status == "queued"
    assert run.autonomy_level == "auto"
    snapshot = json.loads(run.policy_snapshot_json)
    assert snapshot["conditions"]["max_quantity"] == 10
    assert snapshot["paused"] is False


@pytest.mark.asyncio
async def test_high_risk_auto_policy_requires_explicit_high_risk_permission(
    db_session,
):
    user, workspace = await _personal_context(
        db_session,
        "policy-high-risk@example.com",
    )
    db_session.add(
        AgentAutonomyPolicy(
            workspace_id=workspace.id,
            action_id="pricing.update",
            autonomy_level="auto",
            conditions_json=json.dumps({"max_percent": 10}),
            enabled=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()

    decision = await evaluate_autonomy(
        db_session,
        workspace_id=workspace.id,
        definition=get_action_definition("pricing.update"),
        input_data={"old_price": "100", "price": "105"},
    )

    assert decision.autonomy_level == "confirm"
    assert "高风险动作" in decision.reason


@pytest.mark.asyncio
async def test_pause_downgrades_new_auto_work_and_freezes_queued_runs(
    db_session,
):
    user, workspace = await _personal_context(
        db_session,
        "policy-pause@example.com",
    )
    db_session.add(
        AgentAutonomyPolicy(
            workspace_id=workspace.id,
            action_id="inventory.update",
            autonomy_level="auto",
            conditions_json=json.dumps({"max_quantity": 20}),
            enabled=True,
            created_by_user_id=user.id,
        )
    )
    await db_session.commit()
    item = await _work_item(
        db_session,
        workspace,
        user,
        suffix="pause",
    )
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="inventory.update",
        platform="shopify",
        target_type="inventory_item",
        target_id="item-2",
        input_data={"stock_quantity": 5},
        idempotency_key="policy-pause-inventory",
    )
    assert run.status == "queued"

    paused_workspace, frozen = await set_agent_paused(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        paused=True,
    )
    await db_session.commit()

    assert frozen == 1
    assert json.loads(paused_workspace.settings_json)["agent_paused"] is True
    await db_session.refresh(run)
    await db_session.refresh(item)
    assert run.status == "blocked"
    assert run.error_code == "agent_paused"
    assert item.requires_action == "retry"

    decision = await evaluate_autonomy(
        db_session,
        workspace_id=workspace.id,
        definition=get_action_definition("inventory.update"),
        input_data={"stock_quantity": 5},
    )
    assert decision.autonomy_level == "confirm"
    assert decision.paused is True


@pytest.mark.asyncio
async def test_dual_approval_requires_two_distinct_admins(db_session):
    owner = User(
        email="dual-owner@example.com",
        username="dual-owner",
        password_hash="not-used",
    )
    admin = User(
        email="dual-admin@example.com",
        username="dual-admin",
        password_hash="not-used",
    )
    db_session.add_all([owner, admin])
    await db_session.flush()
    workspace = Workspace(
        name="双人审批团队",
        slug=f"dual-team-{uuid4().hex[:8]}",
        type="team",
        owner_user_id=owner.id,
    )
    db_session.add(workspace)
    await db_session.flush()
    db_session.add_all(
        [
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=owner.id,
                role="owner",
            ),
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=admin.id,
                role="admin",
            ),
            AgentAutonomyPolicy(
                workspace_id=workspace.id,
                action_id="pricing.update",
                autonomy_level="confirm",
                conditions_json=json.dumps(
                    {
                        "allow_high_risk": True,
                        "requires_dual_approval": True,
                    }
                ),
                enabled=True,
                created_by_user_id=owner.id,
            ),
        ]
    )
    await db_session.commit()
    item = await _work_item(
        db_session,
        workspace,
        owner,
        suffix="dual",
    )
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=owner.id,
        work_item_id=item.id,
        action_id="pricing.update",
        platform="shopify",
        target_type="product_variant",
        target_id="variant-1",
        input_data={
            "old_price": "100",
            "price": "105",
            "margin_percent": 30,
        },
        idempotency_key="dual-approval-pricing",
    )
    await db_session.commit()

    first = await confirm_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        actor_user_id=owner.id,
    )
    await db_session.commit()
    assert first.status == "awaiting_confirmation"
    await db_session.refresh(item)
    assert item.requires_action == "confirm"

    duplicate = await confirm_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        actor_user_id=owner.id,
    )
    assert duplicate.status == "awaiting_confirmation"

    second = await confirm_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        actor_user_id=admin.id,
    )
    await db_session.commit()

    assert second.status == "queued"
    assert second.confirmed_by_user_id == admin.id
    approvals = (
        await db_session.execute(
            select(ActionApproval).where(
                ActionApproval.action_run_id == run.id
            )
        )
    ).scalars().all()
    assert {item.user_id for item in approvals} == {owner.id, admin.id}
    assert {item.role for item in approvals} == {"owner", "admin"}


@pytest.mark.asyncio
async def test_agent_control_api_persists_pause_and_policy(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "policy-api@example.com",
            "username": "policy-api",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "policy-api@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    await db_session.commit()

    paused = await client.patch(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-control",
        headers=headers,
        json={"paused": True},
    )
    policy = await client.put(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            "/agent-control/policies/inventory.update"
        ),
        headers=headers,
        json={
            "autonomy_level": "auto",
            "conditions": {"max_quantity": 12},
            "enabled": True,
        },
    )
    control = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-control",
        headers=headers,
    )

    assert paused.status_code == 200
    assert paused.json()["paused"] is True
    assert policy.status_code == 200
    assert policy.json()["version"] == 1
    assert control.status_code == 200
    assert control.json()["paused"] is True
    assert control.json()["policies"][0]["action_id"] == "inventory.update"
