"""Temu 自履约受控动作、确认和回读测试。"""

import json

import httpx
import pytest

from app.core.crypto import encrypt_value
from app.models.agent_work import WorkItem
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services import provider_config
from app.services.action_dispatcher import resolve_action_adapter
from app.services.action_previews import build_action_preview
from app.services.action_runtime import plan_action_run
from app.services.temu_fulfillment import TemuFulfillmentService
from app.services.temu_fulfillment_adapter import (
    TemuOrderFulfillmentActionAdapter,
)
from app.services.temu_open_api import TemuOpenApiService
from app.services.workspaces import ensure_personal_workspace


def _configure_temu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_KEY",
        "temu-app-key",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_SECRET",
        "temu-app-secret",
        raising=False,
    )
    provider_config.clear_cache()


def _detail(*, shipped: bool = False) -> dict:
    return {
        "parentOrderMap": {
            "parentOrderSn": "PO-1001",
            "parentOrderStatus": 4 if shipped else 2,
            "regionId": 211,
            "parentOrderTime": 1763700000,
            "updateTime": 1763700100,
            "expectShipLatestTime": 1763800000,
            "parentOrderLabel": [],
            "parentShippingTime": 1763700200 if shipped else 0,
        },
        "orderList": [
            {
                "orderSn": "SO-1001",
                "orderStatus": 4 if shipped else 2,
                "goodsId": 2001,
                "goodsName": "Temu Product",
                "skuId": 3001,
                "quantity": 2,
                "fulfillmentType": "fulfillBySeller",
                "orderShippingTime": 1763700200 if shipped else 0,
                "isCancelledDuringPending": False,
                "buyerName": "Private Buyer",
                "shippingAddress": "private street",
            }
        ],
    }


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
        account_name="Temu Fulfillment Store",
        external_account_id=f"mall-fulfillment-{user.id}",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"temu-secret-token"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": store_type,
                "api_scope_list": (
                    scopes
                    if scopes is not None
                    else [
                        "bg.order.detail.v2.get",
                        "bg.logistics.companies.get",
                        "bg.logistics.shipment.v2.confirm",
                        "bg.logistics.shipment.v2.get",
                    ]
                ),
            }
        ),
    )
    work = WorkItem(
        workspace_id=workspace.id,
        kind="order_exception",
        source="integration",
        title="Temu 订单等待发货",
        summary="需要确认物流信息",
        status="waiting_user",
        requires_action="confirm",
        current_step="等待确认发货",
    )
    db_session.add_all([connection, work])
    await db_session.commit()
    await db_session.refresh(connection)
    await db_session.refresh(work)
    return user, workspace, connection, work


@pytest.mark.asyncio
async def test_temu_fulfillment_preflight_execute_and_verify(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    user, workspace, connection, _work = await _context(
        db_session,
        "temu-fulfill-adapter@example.com",
    )
    state = {"confirmed": False}
    requests: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        api_type = body["type"]
        if api_type == "bg.order.detail.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": _detail(shipped=state["confirmed"]),
                },
            )
        if api_type == "bg.logistics.companies.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": [
                        {
                            "logisticsServiceProviderId": 99,
                            "logisticsServiceProviderName": "UPS",
                        }
                    ],
                },
            )
        if api_type == "bg.logistics.shipment.v2.confirm":
            state["confirmed"] = True
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {"warningMessage": []},
                },
            )
        if api_type == "bg.logistics.shipment.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "shipmentInfoDTO": (
                            [
                                {
                                    "trackingNumber": "1Z999",
                                    "carrierId": 99,
                                    "orderSn": "SO-1001",
                                    "parentOrderSn": "PO-1001",
                                }
                            ]
                            if state["confirmed"]
                            else []
                        )
                    },
                },
            )
        raise AssertionError(f"unexpected api type: {api_type}")

    service = TemuFulfillmentService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "connection_id": str(connection.id),
        "parent_order_sn": "PO-1001",
        "carrier_id": 99,
        "tracking_number": "1Z-999",
        "self_shipping_warehouse_id": "WH-1",
    }

    before = await adapter.preflight(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        input_data=input_data,
    )
    assert before["carrier_name"] == "UPS"
    assert before["item_count"] == 2
    assert "temu-secret-token" not in json.dumps(before)
    assert "private buyer" not in json.dumps(before).lower()
    assert not any(
        item["type"] == "bg.logistics.shipment.v2.confirm"
        for item in requests
    )

    execution = await adapter.execute(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        input_data=input_data,
        idempotency_key="temu-fulfill:PO-1001:1Z999",
    )
    confirmation = next(
        item
        for item in requests
        if item["type"] == "bg.logistics.shipment.v2.confirm"
    )
    assert confirmation["sendType"] == 0
    request_item = confirmation["sendRequestList"][0]
    assert request_item["trackingNumber"] == "1Z999"
    assert request_item["carrierId"] == 99
    assert request_item["selfShippingWarehouseId"] == "WH-1"
    assert request_item["orderSendInfoList"] == [
        {
            "parentOrderSn": "PO-1001",
            "orderSn": "SO-1001",
            "goodsId": 2001,
            "skuId": 3001,
            "quantity": 2,
        }
    ]

    verification = await adapter.verify(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        execution=execution,
    )
    assert verification.matched is True
    assert verification.snapshot["tracking_number"] == "1Z999"
    assert verification.snapshot["order_sn_count"] == 1


@pytest.mark.asyncio
async def test_temu_fulfillment_plan_preview_and_dispatcher(db_session):
    user, workspace, _connection, work = await _context(
        db_session,
        "temu-fulfill-plan@example.com",
    )
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=work.id,
        action_id="temu.orders.fulfill",
        platform="temu",
        target_type="order",
        target_id="PO-1001",
        input_data={
            "connection_id": str(_connection.id),
            "parent_order_sn": "PO-1001",
            "carrier_id": 99,
            "carrier_name": "UPS",
            "tracking_number": "1Z999",
            "self_shipping_warehouse_id": "WH-1",
            "item_count": 2,
        },
        idempotency_key="temu-fulfill-plan-1",
    )
    preview = build_action_preview(run, fallback_title="Temu 发货")
    adapter = await resolve_action_adapter(db_session, run)

    assert run.status == "awaiting_confirmation"
    assert preview.title == "即将确认 Temu 发货"
    assert preview.platform == "temu"
    assert any(
        field.label == "物流单号" and field.value == "1Z999"
        for field in preview.fields
    )
    assert isinstance(adapter, TemuOrderFulfillmentActionAdapter)


@pytest.mark.asyncio
async def test_agent_prepares_temu_fulfillment_without_submitting(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, connection, _work = await _context(
        db_session,
        "temu-fulfill-agent@example.com",
    )
    submitted = {"value": 0}

    async def fake_preflight(self, *, action_id, target_id, input_data):
        assert action_id == "temu.orders.fulfill"
        assert target_id == "PO-1001"
        return {
            "connection_id": str(connection.id),
            "parent_order_sn": "PO-1001",
            "region_id": 211,
            "carrier_id": 99,
            "carrier_name": "UPS",
            "tracking_number": "1Z999",
            "self_shipping_warehouse_id": "WH-1",
            "item_count": 2,
            "order_sns": ["SO-1001"],
            "order_lines": [],
            "already_shipped": False,
        }

    async def fake_execute(self, **kwargs):
        submitted["value"] += 1

    monkeypatch.setattr(
        TemuOrderFulfillmentActionAdapter,
        "preflight",
        fake_preflight,
    )
    monkeypatch.setattr(
        TemuOrderFulfillmentActionAdapter,
        "execute",
        fake_execute,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "fulfill_temu_order",
        {
            "connection_id": str(connection.id),
            "parent_order_sn": "PO-1001",
            "carrier_id": 99,
            "tracking_number": "1Z-999",
            "self_shipping_warehouse_id": "WH-1",
        },
    )

    assert submitted["value"] == 0
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "temu.orders.fulfill"
    assert pending["params"]["connection_id"] == str(connection.id)
    assert pending["params"]["tracking_number"] == "1Z999"


def test_agent_registers_temu_fulfillment_tool():
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "fulfill_temu_order" in names


@pytest.mark.asyncio
async def test_temu_fulfillment_retry_skips_confirm_when_shipped(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    user, workspace, connection, _work = await _context(
        db_session,
        "temu-fulfill-retry@example.com",
    )
    confirm_calls = {"value": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        api_type = body["type"]
        if api_type == "bg.order.detail.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": _detail(shipped=True),
                },
            )
        if api_type == "bg.logistics.companies.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": [
                        {
                            "logisticsServiceProviderId": 99,
                            "logisticsServiceProviderName": "UPS",
                        }
                    ],
                },
            )
        if api_type == "bg.logistics.shipment.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "shipmentInfoDTO": [
                            {
                                "trackingNumber": "1Z999",
                                "carrierId": 99,
                            }
                        ]
                    },
                },
            )
        if api_type == "bg.logistics.shipment.v2.confirm":
            confirm_calls["value"] += 1
            raise AssertionError("已发货重试不应再次确认")
        raise AssertionError(f"unexpected api type: {api_type}")

    service = TemuFulfillmentService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "connection_id": str(connection.id),
        "parent_order_sn": "PO-1001",
        "carrier_id": 99,
        "tracking_number": "1Z999",
    }

    snapshot = await adapter.preflight(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        input_data=input_data,
        idempotency_key="temu-fulfill-retry",
    )
    verification = await adapter.verify(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        execution=execution,
    )

    assert snapshot["already_shipped"] is True
    assert confirm_calls["value"] == 0
    assert verification.matched is True


@pytest.mark.asyncio
async def test_temu_fulfillment_rejects_crossborder_and_missing_scope(
    db_session,
):
    _user, workspace, crossborder, _work = await _context(
        db_session,
        "temu-fulfill-crossborder@example.com",
        store_type="crossborder",
    )
    adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=_user.id,
        workspace_id=workspace.id,
    )
    with pytest.raises(ValueError, match="LOCAL/SEMI"):
        await adapter.preflight(
            action_id="temu.orders.fulfill",
            target_id="PO-1001",
            input_data={
                "connection_id": str(crossborder.id),
                "parent_order_sn": "PO-1001",
                "carrier_id": 99,
                "tracking_number": "1Z999",
            },
        )

    _user2, workspace2, incomplete, _work2 = await _context(
        db_session,
        "temu-fulfill-scope@example.com",
        scopes=["bg.logistics.shipment.v2.confirm"],
    )
    incomplete_adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=_user2.id,
        workspace_id=workspace2.id,
    )
    with pytest.raises(ValueError, match="scope"):
        await incomplete_adapter.preflight(
            action_id="temu.orders.fulfill",
            target_id="PO-1001",
            input_data={
                "connection_id": str(incomplete.id),
                "parent_order_sn": "PO-1001",
                "carrier_id": 99,
                "tracking_number": "1Z999",
            },
        )


@pytest.mark.asyncio
async def test_temu_confirm_already_shipped_error_remains_recoverable(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    user, workspace, connection, _work = await _context(
        db_session,
        "temu-fulfill-already@example.com",
    )
    state = {"confirm_called": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        api_type = body["type"]
        if api_type == "bg.order.detail.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": _detail(shipped=False),
                },
            )
        if api_type == "bg.logistics.companies.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": [
                        {
                            "logisticsServiceProviderId": 99,
                            "logisticsServiceProviderName": "UPS",
                        }
                    ],
                },
            )
        if api_type == "bg.logistics.shipment.v2.confirm":
            state["confirm_called"] = True
            return httpx.Response(
                200,
                json={
                    "success": False,
                    "errorCode": 120012004,
                    "errorMsg": "Order already shipped",
                },
            )
        if api_type == "bg.logistics.shipment.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "shipmentInfoDTO": [
                            {
                                "trackingNumber": "1Z999",
                                "carrierId": 99,
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"unexpected api type: {api_type}")

    service = TemuFulfillmentService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "connection_id": str(connection.id),
        "parent_order_sn": "PO-1001",
        "carrier_id": 99,
        "tracking_number": "1Z999",
    }
    execution = await adapter.execute(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        input_data=input_data,
        idempotency_key="temu-fulfill-already",
    )
    verification = await adapter.verify(
        action_id="temu.orders.fulfill",
        target_id="PO-1001",
        execution=execution,
    )

    assert state["confirm_called"] is True
    assert verification.matched is True


@pytest.mark.asyncio
async def test_temu_fulfillment_rejects_wrong_carrier_and_partner_warehouse(
    db_session,
):
    user, workspace, connection, _work = await _context(
        db_session,
        "temu-fulfill-preflight@example.com",
    )

    class FakeService:
        fulfillment_type = "fulfillBySeller"

        async def get_order_detail(self, **kwargs):
            line = {
                "order_sn": "SO-1001",
                "goods_id": 2001,
                "sku_id": 3001,
                "quantity": 2,
                "fulfillment_type": self.fulfillment_type,
                "order_status": 2,
                "shipping_time": 0,
                "is_cancelled_during_pending": False,
            }
            return {
                "connection_id": str(connection.id),
                "parent_order_sn": "PO-1001",
                "region_id": 211,
                "lines": [line],
                "active_lines": [line],
                "item_count": 2,
                "shipped": False,
            }

        async def list_carriers(self, **kwargs):
            return [{"carrier_id": 99, "name": "UPS"}]

        async def get_shipment(self, **kwargs):
            return {"tracking_numbers": []}

        async def confirm_shipment(self, **kwargs):
            raise AssertionError("预检失败不应提交")

    fake = FakeService()
    adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=fake,
    )
    with pytest.raises(ValueError, match="承运商"):
        await adapter.preflight(
            action_id="temu.orders.fulfill",
            target_id="PO-1001",
            input_data={
                "connection_id": str(connection.id),
                "parent_order_sn": "PO-1001",
                "carrier_id": 100,
                "tracking_number": "1Z999",
            },
        )

    fake.fulfillment_type = "fulfillByCooperativeWarehouse"
    with pytest.raises(ValueError, match="合作仓"):
        await adapter.preflight(
            action_id="temu.orders.fulfill",
            target_id="PO-1001",
            input_data={
                "connection_id": str(connection.id),
                "parent_order_sn": "PO-1001",
                "carrier_id": 99,
                "tracking_number": "1Z999",
            },
        )


@pytest.mark.asyncio
async def test_temu_fulfillment_translates_address_change_error(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    user, workspace, connection, _work = await _context(
        db_session,
        "temu-fulfill-address-change@example.com",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        api_type = body["type"]
        if api_type == "bg.order.detail.v2.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": _detail(),
                },
            )
        if api_type == "bg.logistics.companies.get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": [
                        {
                            "logisticsServiceProviderId": 99,
                            "logisticsServiceProviderName": "UPS",
                        }
                    ],
                },
            )
        if api_type == "bg.logistics.shipment.v2.confirm":
            return httpx.Response(
                200,
                json={
                    "success": False,
                    "errorCode": 120012023,
                    "errorMsg": "Buyer requested address change",
                },
            )
        raise AssertionError(f"unexpected api type: {api_type}")

    adapter = TemuOrderFulfillmentActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=TemuFulfillmentService(
            db_session,
            user_id=user.id,
            open_api=TemuOpenApiService(
                transport=httpx.MockTransport(handler)
            ),
        ),
    )
    with pytest.raises(ValueError, match="改地址"):
        await adapter.execute(
            action_id="temu.orders.fulfill",
            target_id="PO-1001",
            input_data={
                "connection_id": str(connection.id),
                "parent_order_sn": "PO-1001",
                "carrier_id": 99,
                "tracking_number": "1Z999",
            },
            idempotency_key="temu-fulfill-address-change",
        )
