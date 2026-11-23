"""Temu 自发货只读验收诊断测试。"""

import json
from uuid import uuid4

import pytest

from app.services.temu_fulfillment_readiness import (
    build_temu_fulfillment_readiness_report,
    readiness_exit_code,
    run_temu_fulfillment_readiness,
)


def _snapshot():
    return {
        "connection_id": str(uuid4()),
        "parent_order_sn": "PO-1001",
        "region_id": 211,
        "carrier_id": 99,
        "carrier_name": "UPS",
        "tracking_number": "1Z999AA10123456784",
        "self_shipping_warehouse_id": "WH-1",
        "item_count": 2,
        "order_sns": ["SO-1001"],
        "order_lines": [
            {
                "order_sn": "SO-1001",
                "goods_id": 2001,
                "sku_id": 3001,
                "quantity": 2,
            }
        ],
        "already_shipped": False,
    }


def test_readiness_report_masks_tracking_and_never_enables_submit():
    report = build_temu_fulfillment_readiness_report(_snapshot())

    assert report["ready"] is True
    assert report["status"] == "ready"
    assert report["submitted"] is False
    assert report["action_id"] == "temu.orders.fulfill"
    assert report["tracking_number_masked"] == "1Z99...6784"
    assert report["self_shipping_warehouse_present"] is True
    serialized = json.dumps(report, ensure_ascii=False).lower()
    assert "temu-secret-token" not in serialized
    assert "private buyer" not in serialized


@pytest.mark.asyncio
async def test_readiness_runner_uses_preflight_without_submit(db_session):
    connection_id = uuid4()
    user_id = uuid4()
    workspace_id = uuid4()
    calls = {"preflight": 0, "execute": 0}

    class FakeAdapter:
        async def preflight(self, *, action_id, target_id, input_data):
            calls["preflight"] += 1
            assert action_id == "temu.orders.fulfill"
            assert target_id == "PO-1001"
            assert input_data["connection_id"] == str(connection_id)
            return _snapshot() | {
                "connection_id": str(connection_id)
            }

        async def execute(self, **kwargs):
            calls["execute"] += 1
            raise AssertionError("诊断工具不能提交发货")

    report = await run_temu_fulfillment_readiness(
        db_session,
        user_id=user_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        parent_order_sn="PO-1001",
        carrier_id=99,
        tracking_number="1Z999AA10123456784",
        self_shipping_warehouse_id="WH-1",
        adapter=FakeAdapter(),
    )

    assert report["ready"] is True
    assert report["submitted"] is False
    assert calls == {"preflight": 1, "execute": 0}


def test_readiness_exit_code_is_zero_only_when_ready():
    assert readiness_exit_code({"ready": True}) == 0
    assert readiness_exit_code({"ready": False}) == 2


def test_blocked_readiness_report_keeps_actionable_error():
    report = build_temu_fulfillment_readiness_report(
        error="缺少 Temu 自发货 scope",
        connection_id=str(uuid4()),
        parent_order_sn="PO-1001",
    )

    assert report["ready"] is False
    assert report["status"] == "blocked"
    assert report["submitted"] is False
    assert report["blockers"] == ["缺少 Temu 自发货 scope"]
    assert report["next_step"] == "修复阻断项后重新执行只读预检"
