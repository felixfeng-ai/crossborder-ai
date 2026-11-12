"""用户自动化开关 API 与权限测试。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.user import User


async def _register(client, *, plan: str = "professional") -> tuple[dict, str]:
    email = f"automation-{uuid.uuid4().hex[:8]}@test.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }, email


@pytest.mark.asyncio
async def test_paid_user_reads_defaults_and_updates_preferences(
    client,
    db_session,
):
    headers, email = await _register(client)
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.plan = "professional"
    await db_session.flush()

    response = await client.get("/api/v1/settings/automation", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["eligible"] is True
    assert {item["key"]: item["enabled"] for item in payload["tasks"]} == {
        "store_check": True,
        "operations_monitor": True,
        "shopify_sync": True,
        "ab_evaluation": True,
    }

    updated = await client.put(
        "/api/v1/settings/automation",
        json={
            "daily_store_check": False,
            "shopify_auto_sync": False,
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    tasks = {item["key"]: item for item in updated.json()["tasks"]}
    assert tasks["store_check"]["enabled"] is False
    assert tasks["shopify_sync"]["enabled"] is False
    assert tasks["operations_monitor"]["enabled"] is True

    reread = await client.get("/api/v1/settings/automation", headers=headers)
    assert reread.status_code == 200
    assert {
        item["key"]: item["enabled"]
        for item in reread.json()["tasks"]
    }["store_check"] is False


@pytest.mark.asyncio
async def test_free_user_cannot_enable_paid_automation(client, db_session):
    headers, email = await _register(client, plan="free")
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.plan = "free"
    await db_session.flush()

    response = await client.put(
        "/api/v1/settings/automation",
        json={"daily_operations_monitor": True},
        headers=headers,
    )

    assert response.status_code == 403
    assert "Standard" in response.json()["detail"]


@pytest.mark.asyncio
async def test_automation_preferences_are_isolated_by_user(client, db_session):
    first_headers, first_email = await _register(client)
    second_headers, second_email = await _register(client)
    for email in (first_email, second_email):
        user = (
            await db_session.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.plan = "professional"
    await db_session.flush()

    await client.put(
        "/api/v1/settings/automation",
        json={"store_check": False},
        headers=first_headers,
    )
    second = await client.get(
        "/api/v1/settings/automation",
        headers=second_headers,
    )
    assert second.status_code == 200
    assert {
        item["key"]: item["enabled"] for item in second.json()["tasks"]
    }["store_check"] is True
