"""运营看板与预警的工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.operation_alert import OperationAlert
from app.models.product import Product
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
        name="Operations Team",
        slug="operations-team",
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
async def test_operations_digest_and_alerts_are_workspace_scoped(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    personal_product = Product(
        user_id=user.id,
        workspace_id=personal.id,
        title="Personal product",
        url="https://example.com/personal-operations",
    )
    team_product = Product(
        user_id=user.id,
        workspace_id=team.id,
        title="Team product",
        url="https://example.com/team-operations",
    )
    db_session.add_all([personal_product, team_product])
    await db_session.flush()
    personal_alert = OperationAlert(
        user_id=user.id,
        workspace_id=personal.id,
        product_id=personal_product.id,
        alert_type="low_stock",
        severity="warning",
        title="Personal alert",
        message="personal",
        status="open",
    )
    team_alert = OperationAlert(
        user_id=user.id,
        workspace_id=team.id,
        product_id=team_product.id,
        alert_type="out_of_stock",
        severity="critical",
        title="Team alert",
        message="team",
        status="open",
    )
    db_session.add_all([personal_alert, team_alert])
    await db_session.commit()
    headers = {
        **auth_headers,
        "X-Workspace-Id": str(team.id),
    }

    digest = await client.get("/api/v1/operations/digest", headers=headers)
    alerts = await client.get("/api/v1/operations/alerts", headers=headers)

    assert digest.status_code == 200
    assert digest.json()["total"] == 1
    assert digest.json()["priority_items"][0]["title"] == "Team alert"
    assert alerts.status_code == 200
    assert [item["id"] for item in alerts.json()["items"]] == [
        str(team_alert.id)
    ]


@pytest.mark.asyncio
async def test_operation_alert_update_rejects_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    alert = OperationAlert(
        user_id=user.id,
        workspace_id=team.id,
        alert_type="out_of_stock",
        severity="critical",
        title="Team alert",
        message="team",
        status="open",
    )
    db_session.add(alert)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/operations/alerts/{alert.id}",
        json={"status": "acknowledged"},
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_monitor_settings_are_saved_per_workspace(
    client,
    auth_headers,
    db_session,
):
    _user, personal, team = await _workspace_pair(db_session)

    updated = await client.put(
        "/api/v1/operations/settings",
        json={
            "target_margin_rate": 42,
            "low_stock_days": 10,
            "lead_time_days": 14,
            "safety_stock_days": 3,
            "platform_fee_rate": 0.15,
            "shipping_cost": 0,
            "cost_increase_alert_rate": 8,
        },
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )
    personal_settings = await client.get(
        "/api/v1/operations/settings",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert updated.status_code == 200
    assert updated.json()["target_margin_rate"] == 42
    assert personal_settings.status_code == 200
    assert personal_settings.json()["target_margin_rate"] == 25
