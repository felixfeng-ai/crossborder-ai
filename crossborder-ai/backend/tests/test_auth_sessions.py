"""可撤销设备会话、刷新令牌轮换和重放测试。"""

import uuid
import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.security import create_access_token, decode_token
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_sessions import (
    RefreshTokenRejected,
    create_user_session,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    validate_user_session,
)


async def _register(client, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@", 1)[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_register_issues_short_lived_access_and_revocable_session(client):
    payload = await _register(client, "session-register@example.com")
    access_payload = decode_token(payload["access_token"])
    expires_at = datetime.fromtimestamp(
        access_payload["exp"],
        tz=timezone.utc,
    )
    lifetime = expires_at - datetime.now(timezone.utc)

    assert payload["refresh_token"]
    assert payload["session_id"] == access_payload["sid"]
    assert access_payload["type"] == "access"
    assert 0 < lifetime.total_seconds() <= 16 * 60

    me = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {payload['access_token']}"
        },
    )
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_refresh_rotates_once_and_replay_revokes_session(client):
    registered = await _register(client, "session-rotate@example.com")

    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registered["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    rotated = refreshed.json()
    assert rotated["refresh_token"] != registered["refresh_token"]
    assert rotated["session_id"] == registered["session_id"]

    replay = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registered["refresh_token"]},
    )
    assert replay.status_code == 401

    revoked_access = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {rotated['access_token']}"
        },
    )
    assert revoked_access.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_current_access_and_refresh_token(client):
    registered = await _register(client, "session-logout@example.com")
    headers = {
        "Authorization": f"Bearer {registered['access_token']}"
    }

    logged_out = await client.post("/api/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 204

    me = await client.get("/api/v1/auth/me", headers=headers)
    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registered["refresh_token"]},
    )
    assert me.status_code == 401
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_revokes_every_device(client):
    registered = await _register(client, "session-logout-all@example.com")
    second = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "session-logout-all@example.com",
            "password": "testpass123",
        },
        headers={"X-Device-Name": "second-device"},
    )
    assert second.status_code == 200
    second_headers = {
        "Authorization": f"Bearer {second.json()['access_token']}"
    }

    logged_out = await client.post(
        "/api/v1/auth/logout-all",
        headers=second_headers,
    )
    assert logged_out.status_code == 204
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {registered['access_token']}"
            },
        )
    ).status_code == 401
    assert (
        await client.get("/api/v1/auth/me", headers=second_headers)
    ).status_code == 401


@pytest.mark.asyncio
async def test_session_list_and_revoke_are_owner_scoped(client):
    first = await _register(client, "session-list-a@example.com")
    first_headers = {
        "Authorization": f"Bearer {first['access_token']}"
    }
    second_device = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "session-list-a@example.com",
            "password": "testpass123",
        },
        headers={"X-Device-Name": "second-device"},
    )
    assert second_device.status_code == 200
    second_payload = second_device.json()

    listed = await client.get(
        "/api/v1/auth/sessions",
        headers=first_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    assert sum(
        item["current"] for item in listed.json()["items"]
    ) == 1

    other = await _register(client, "session-list-b@example.com")
    other_headers = {
        "Authorization": f"Bearer {other['access_token']}"
    }
    hidden = await client.delete(
        f"/api/v1/auth/sessions/{second_payload['session_id']}",
        headers=other_headers,
    )
    assert hidden.status_code == 404

    revoked = await client.delete(
        f"/api/v1/auth/sessions/{second_payload['session_id']}",
        headers=first_headers,
    )
    assert revoked.status_code == 204
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {second_payload['access_token']}"
            },
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_change_password_revokes_old_sessions_and_issues_new_one(client):
    registered = await _register(client, "session-password@example.com")
    headers = {
        "Authorization": f"Bearer {registered['access_token']}"
    }

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "testpass123",
            "new_password": "newtestpass456",
        },
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    renewed = changed.json()

    assert (
        await client.get("/api/v1/auth/me", headers=headers)
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": registered["refresh_token"]},
        )
    ).status_code == 401
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {renewed['access_token']}"
            },
        )
    ).status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "session-password@example.com",
            "password": "testpass123",
        },
    )
    new_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "session-password@example.com",
            "password": "newtestpass456",
        },
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_expired_device_session_rejects_access_and_refresh(
    client,
    db_session,
):
    registered = await _register(client, "session-expired@example.com")
    session = await db_session.get(
        UserSession,
        uuid.UUID(registered["session_id"]),
    )
    assert session is not None
    session.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await db_session.commit()

    me = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {registered['access_token']}"
        },
    )
    refreshed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registered["refresh_token"]},
    )

    assert me.status_code == 401
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_legacy_access_token_without_session_id_is_rejected(
    client,
    auth_headers,
):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200

    user_id = decode_token(
        auth_headers["Authorization"].removeprefix("Bearer ")
    )["sub"]
    legacy_token = create_access_token(subject=user_id)
    rejected = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {legacy_token}"},
    )
    assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_refresh_is_atomic_with_independent_sessions(
    tmp_path,
):
    db_path = tmp_path / "session-concurrency.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        connect_args={"timeout": 10},
    )
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(
            email="session-concurrent@example.com",
            username="session-concurrent",
            password_hash="not-used",
        )
        db.add(user)
        await db.flush()
        tokens = await create_user_session(db, user)
        await db.commit()

    async def rotate():
        async with factory() as db:
            try:
                await rotate_refresh_token(db, tokens["refresh_token"])
                await db.commit()
                return 200
            except RefreshTokenRejected:
                await db.commit()
                return 401

    results = await asyncio.gather(rotate(), rotate())
    await engine.dispose()

    assert sorted(results) == [200, 401]


@pytest.mark.asyncio
async def test_auth_session_service_expiry_inactive_and_revoke_paths(
    tmp_path,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'session-service.db').as_posix()}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        user = User(
            email="session-service@example.com",
            username="session-service",
            password_hash="not-used",
        )
        db.add(user)
        await db.flush()
        first = await create_user_session(db, user)
        second = await create_user_session(db, user)
        await db.commit()

        first_session = await db.get(
            UserSession,
            uuid.UUID(first["session_id"]),
        )
        assert await validate_user_session(
            db,
            session_id=first_session.id,
            user_id=user.id,
        ) is not None
        assert not await revoke_session(
            db,
            session_id=first_session.id,
            user_id=uuid.uuid4(),
            reason="wrong_owner",
        )
        assert await revoke_session(
            db,
            session_id=first_session.id,
            user_id=user.id,
            reason="explicit_revoke",
        )

        second_session = await db.get(
            UserSession,
            uuid.UUID(second["session_id"]),
        )
        second_session.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(RefreshTokenRejected):
            await rotate_refresh_token(db, second["refresh_token"])

        third = await create_user_session(db, user)
        user.deleted_at = datetime.now(timezone.utc)
        with pytest.raises(RefreshTokenRejected):
            await rotate_refresh_token(db, third["refresh_token"])
        assert await revoke_all_sessions(
            db,
            user_id=user.id,
            reason="cleanup",
        ) >= 1
        await db.commit()

    await engine.dispose()
