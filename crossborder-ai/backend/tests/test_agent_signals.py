"""Agent 信号归一化、任务去重与同步游标测试。"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models.agent_signal import AgentSignal
from app.models.agent_work import WorkItem
from app.models.user import User
from app.services.agent_signals import (
    ingest_agent_signal,
    resolve_agent_signal,
    save_integration_cursor,
)
from app.services.workspaces import ensure_personal_workspace


async def _workspace(db_session, email: str):
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


@pytest.mark.asyncio
async def test_same_signal_updates_evidence_without_duplicate_work(db_session):
    user, workspace = await _workspace(
        db_session,
        "signals-dedupe@example.com",
    )
    first = await ingest_agent_signal(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        source_type="order",
        source_id="order-1001",
        signal_type="order_delay",
        severity="urgent",
        title="订单将在四小时后超时",
        summary="供应商尚未揽收。",
        payload={"remaining_hours": 4, "carrier": "UPS"},
        fingerprint="order:order-1001:delay",
    )
    second = await ingest_agent_signal(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        source_type="order",
        source_id="order-1001",
        signal_type="order_delay",
        severity="urgent",
        title="订单将在三小时后超时",
        summary="供应商仍未揽收。",
        payload={"remaining_hours": 3, "carrier": "UPS"},
        fingerprint="order:order-1001:delay",
    )
    await db_session.commit()

    signal_count = (
        await db_session.execute(
            select(func.count()).select_from(AgentSignal)
        )
    ).scalar_one()
    work_count = (
        await db_session.execute(
            select(func.count()).select_from(WorkItem)
        )
    ).scalar_one()
    assert first.created is True
    assert second.created is False
    assert signal_count == 1
    assert work_count == 1
    assert second.signal.version == 1
    assert "remaining_hours" in second.signal.payload_json
    assert "3" in second.signal.payload_json


@pytest.mark.asyncio
async def test_resolved_signal_closes_work_and_reappearance_creates_new_version(
    db_session,
):
    user, workspace = await _workspace(
        db_session,
        "signals-reopen@example.com",
    )
    ingested = await ingest_agent_signal(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        source_type="inventory",
        source_id="sku-1",
        signal_type="inventory_low",
        severity="attention",
        title="SKU 库存低于阈值",
        summary="库存只剩 2 件。",
        payload={"stock": 2},
        fingerprint="inventory:sku-1:low",
    )
    resolved = await resolve_agent_signal(
        db_session,
        workspace_id=workspace.id,
        signal_id=ingested.signal.id,
        summary="库存已补货。",
    )
    await db_session.commit()
    work_item = await db_session.get(WorkItem, ingested.work_item.id)
    assert resolved.status == "resolved"
    assert work_item.status == "succeeded"

    reappeared = await ingest_agent_signal(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        source_type="inventory",
        source_id="sku-1",
        signal_type="inventory_low",
        severity="attention",
        title="SKU 库存再次低于阈值",
        summary="库存只剩 1 件。",
        payload={"stock": 1},
        fingerprint="inventory:sku-1:low",
    )
    await db_session.commit()

    assert reappeared.created is True
    assert reappeared.signal.version == 2
    assert reappeared.signal.id != ingested.signal.id


@pytest.mark.asyncio
async def test_integration_cursor_is_upserted_with_overlap(db_session):
    _user, workspace = await _workspace(
        db_session,
        "signals-cursor@example.com",
    )
    first = await save_integration_cursor(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        resource_type="orders",
        cursor_value="2026-11-18T10:00:00Z",
        overlap_seconds=300,
    )
    second = await save_integration_cursor(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        resource_type="orders",
        cursor_value="2026-11-18T10:05:00Z",
        overlap_seconds=600,
    )
    await db_session.commit()

    assert first.id == second.id
    assert second.cursor_value == "2026-11-18T10:05:00Z"
    assert second.overlap_seconds == 600
    assert second.last_success_at is not None
