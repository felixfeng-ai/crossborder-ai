"""Temu LOCAL/SEMI 订单巡检、工作项和游标测试。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_signal import AgentSignal, IntegrationCursor
from app.models.agent_work import WorkItem
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services.temu_order_signal_sync import (
    sync_all_temu_order_signals,
    sync_temu_order_signals,
)
from app.services.scheduler import SchedulerService
from app.services.workspaces import ensure_personal_workspace


async def _context(
    db_session,
    email: str,
    *,
    store_type: str = "local",
    scopes: list[str] | None = None,
):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Monitoring Store",
        external_account_id=f"mall-{user.id}",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"temu-secret-token"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": store_type,
                "api_scope_list": (
                    scopes
                    if scopes is not None
                    else ["bg.order.list.v2.get"]
                ),
            }
        ),
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)
    return user, workspace, connection


def _order(
    order_sn: str,
    *,
    warning: bool = True,
    shipped: bool = False,
    deadline_hours: int = 4,
    updated_time: int | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    deadline = int(
        (now + timedelta(hours=deadline_hours)).timestamp()
    )
    return {
        "parent_order_sn": order_sn,
        "parent_order_status": 2,
        "created_time": int((now - timedelta(hours=8)).timestamp()),
        "updated_time": (
            updated_time
            if updated_time is not None
            else int(now.timestamp())
        ),
        "expect_ship_latest_time": deadline,
        "fulfillment_warnings": (
            ["soon_to_be_overdue"] if warning else []
        ),
        "labels": [],
        "paid_shipping_amount": {"amount": 4.99, "currency": "USD"},
        "orders": [
            {
                "order_sn": f"{order_sn}-1",
                "goods_id": "goods-1",
                "goods_name": "Temu Product",
                "sku_id": "sku-1",
                "quantity": 2,
                "shipping_time": (
                    int(now.timestamp()) if shipped else 0
                ),
                "package_abnormal_types": [],
            }
        ],
    }


@pytest.mark.asyncio
async def test_temu_order_monitoring_creates_idempotent_work_item(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _user, workspace, connection = await _context(
        db_session,
        "temu-order-monitor@example.com",
    )

    async def fake_list(self, **kwargs):
        assert kwargs["connection_id"] == connection.id
        return {
            "connection_id": str(connection.id),
            "total": 1,
            "items": [_order("PO-1001")],
        }

    monkeypatch.setattr(
        "app.services.temu_order_signal_sync."
        "TemuOrderReadService.list_orders",
        fake_list,
    )

    first = await sync_temu_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()
    second = await sync_temu_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id,
                AgentSignal.signal_type == "temu_order_awaiting_shipment",
            )
        )
    ).scalar_one()
    work_item = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    cursor = (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id,
                IntegrationCursor.resource_type == "temu_orders",
            )
        )
    ).scalar_one()
    payload = json.loads(signal.payload_json)

    assert first["signals_created"] == 1
    assert second["signals_updated"] == 1
    assert work_item.kind == "order_exception"
    assert work_item.requires_action == "none"
    assert payload["parent_order_sn"] == "PO-1001"
    assert payload["item_count"] == 2
    assert payload["fulfillment_warnings"] == ["soon_to_be_overdue"]
    assert "temu-secret-token" not in json.dumps(payload)
    assert "private buyer" not in json.dumps(payload).lower()
    assert cursor.cursor_value


@pytest.mark.asyncio
async def test_shipped_temu_order_resolves_existing_work_item(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _user, workspace, connection = await _context(
        db_session,
        "temu-order-shipped@example.com",
    )
    state = {"shipped": False}

    async def fake_list(self, **kwargs):
        return {
            "total": 1,
            "items": [
                _order(
                    "PO-SHIPPED",
                    warning=not state["shipped"],
                    shipped=state["shipped"],
                )
            ],
        }

    monkeypatch.setattr(
        "app.services.temu_order_signal_sync."
        "TemuOrderReadService.list_orders",
        fake_list,
    )
    await sync_temu_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    state["shipped"] = True
    result = await sync_temu_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    work_item = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert result["signals_resolved"] == 1
    assert signal.status == "resolved"
    assert work_item.status == "succeeded"


@pytest.mark.asyncio
async def test_temu_order_monitoring_reads_all_pages_before_cursor(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _user, workspace, connection = await _context(
        db_session,
        "temu-order-pages@example.com",
    )
    pages_seen = []

    async def fake_list(self, **kwargs):
        page = kwargs["page_number"]
        pages_seen.append(page)
        return {
            "total": 101,
            "items": [
                _order(
                    f"PO-PAGE-{page}-{index}",
                    warning=False,
                    deadline_hours=48,
                )
                for index in range(100 if page == 1 else 1)
            ],
        }

    monkeypatch.setattr(
        "app.services.temu_order_signal_sync."
        "TemuOrderReadService.list_orders",
        fake_list,
    )
    result = await sync_temu_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    cursor = (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert pages_seen == [1, 2]
    assert result["pages_scanned"] == 2
    assert cursor.cursor_value


@pytest.mark.asyncio
async def test_temu_order_monitoring_failure_keeps_cursor_and_signals_empty(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _user, workspace, connection = await _context(
        db_session,
        "temu-order-page-failure@example.com",
    )
    workspace_id = workspace.id

    async def fake_list(self, **kwargs):
        if kwargs["page_number"] == 1:
            return {"total": 101, "items": [_order("PO-FAIL-1")]}
        raise ValueError("Temu 第 2 页读取失败")

    monkeypatch.setattr(
        "app.services.temu_order_signal_sync."
        "TemuOrderReadService.list_orders",
        fake_list,
    )
    with pytest.raises(ValueError, match="第 2 页"):
        await sync_temu_order_signals(
            db_session,
            workspace_id=workspace.id,
            connection=connection,
        )
    await db_session.rollback()

    assert (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_all_temu_sync_skips_crossborder_without_api_call(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _user, workspace, _connection = await _context(
        db_session,
        "temu-order-crossborder@example.com",
        store_type="crossborder",
    )

    async def fake_list(self, **kwargs):
        raise AssertionError("跨境店铺不应调用 LOCAL/SEMI 订单接口")

    monkeypatch.setattr(
        "app.services.temu_order_signal_sync."
        "TemuOrderReadService.list_orders",
        fake_list,
    )
    result = await sync_all_temu_order_signals(db_session)
    await db_session.commit()

    assert result["connections_scanned"] == 1
    assert result["connections_skipped"] == 1
    assert result["connections_succeeded"] == 0
    assert (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id
            )
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_all_temu_sync_isolates_single_store_failure(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, failing = await _context(
        db_session,
        "temu-order-store-isolation@example.com",
    )
    healthy = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Healthy Store",
        external_account_id=f"mall-healthy-{user.id}",
        marketplace_id="eu",
        credentials=encrypt_value('{"access_token":"temu-healthy-token"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "semi",
                "api_scope_list": ["bg.order.list.v2.get"],
            }
        ),
    )
    db_session.add(healthy)
    await db_session.commit()
    await db_session.refresh(healthy)

    async def fake_list(self, **kwargs):
        if kwargs["connection_id"] == failing.id:
            raise ValueError("Temu 失败店铺接口不可用")
        return {"total": 1, "items": [_order("PO-HEALTHY")]}

    monkeypatch.setattr(
        "app.services.temu_order_signal_sync."
        "TemuOrderReadService.list_orders",
        fake_list,
    )
    result = await sync_all_temu_order_signals(db_session)
    await db_session.commit()

    assert result["connections_scanned"] == 2
    assert result["connections_failed"] == 1
    assert result["connections_succeeded"] == 1
    assert result["failures"][0]["connection_id"] == str(failing.id)
    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    assert json.loads(signal.payload_json)["parent_order_sn"] == "PO-HEALTHY"


@pytest.mark.asyncio
async def test_scheduler_registers_temu_order_monitoring(
    monkeypatch: pytest.MonkeyPatch,
):
    scheduler = SchedulerService()
    monkeypatch.setattr(scheduler.scheduler, "start", lambda: None)

    await scheduler.start()

    job = scheduler.scheduler.get_job("temu_order_signal_sync")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 15 * 60
