"""管理员白名单的持久化与审计契约。"""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core import access_control
from app.models.admin_audit_log import AdminAuditLog
from app.models.system_config import SystemConfig


async def _admin_headers(client: AsyncClient) -> dict:
    credentials = {
        "email": "admin@veyaship.com",
        "username": "admin-access",
        "password": "testpass123",
    }
    response = await client.post("/api/v1/auth/register", json=credentials)
    if response.status_code == 409:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": credentials["email"], "password": credentials["password"]},
        )
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_whitelist_changes_persist_and_are_audited(client: AsyncClient, db_session):
    headers = await _admin_headers(client)
    email = f"access-{uuid.uuid4().hex[:8]}@example.com"

    try:
        added = await client.post(
            "/api/v1/settings/whitelist/add",
            json={"email": email},
            headers=headers,
        )
        assert added.status_code == 200, added.text

        row = (
            await db_session.execute(
                select(SystemConfig).where(
                    SystemConfig.key == access_control.WHITELIST_CONFIG_KEY
                )
            )
        ).scalar_one()
        assert email in json.loads(row.value)

        listed = await client.get("/api/v1/settings/whitelist", headers=headers)
        assert email in listed.json()["emails"]

        removed = await client.post(
            "/api/v1/settings/whitelist/remove",
            json={"email": email},
            headers=headers,
        )
        assert removed.status_code == 200, removed.text

        await access_control.refresh(db_session)
        listed_after = await client.get("/api/v1/settings/whitelist", headers=headers)
        assert email not in listed_after.json()["emails"]

        audit_actions = (
            await db_session.execute(
                select(AdminAuditLog.action).where(
                    AdminAuditLog.target_id == email
                )
            )
        ).scalars().all()
        assert "access.whitelist.add" in audit_actions
        assert "access.whitelist.remove" in audit_actions
    finally:
        access_control.WHITELIST_EMAILS.discard(email)
