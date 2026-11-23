"""Amazon FBM 确认发货动作、回读和隐私边界测试。"""

import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.action_run import ActionRun
from app.models.agent_work import WorkItem
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services.action_dispatcher import resolve_action_adapter
from app.services.action_previews import build_action_preview
from app.services.action_runtime import plan_action_run
from app.services.amazon_fulfillment_adapter import (
    AmazonOrderFulfillmentActionAdapter,
)
from app.services.amazon_orders import AmazonOrdersService
from app.services.workspaces import ensure_personal_workspace


def _order(
    *,
    status: str = "UNSHIPPED",
    fulfilled_by: str = "MERCHANT",
    quantity: int = 2,
    fulfilled_quantity: int = 0,
    packages: list[dict] | None = None,
):
    return {
        "orderId": "111-2222222-3333333",
        "createdTime": datetime.now(timezone.utc).isoformat(),
        "lastUpdatedTime": datetime.now(timezone.utc).isoformat(),
        "salesChannel": {"marketplaceId": "ATVPDKIKX0DER"},
        "fulfillment": {
            "fulfilledBy": fulfilled_by,
            "fulfillmentStatus": status,
        },
        "orderItems": [
            {
                "orderItemId": "item-1",
                "quantityOrdered": quantity,
                "fulfillment": {
                    "quantityFulfilled": fulfilled_quantity,
                },
                "product": {
                    "sellerSku": "SKU-1",
                    "title": "Test product",
                },
            }
        ],
        "packages": packages or [],
        "buyer": {
            "email": "private@example.com",
            "name": "Private Buyer",
        },
        "recipient": {"address": "private street"},
    }


async def _context(db_session, email: str):
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
        platform="amazon",
        account_name="Amazon US",
        external_account_id="A1SELLER",
        marketplace_id="ATVPDKIKX0DER",
        credentials=encrypt_value(
            json.dumps({"refresh_token": "Atzr|refresh-token"})
        ),
        status="active",
        metadata_json=json.dumps(
            {
                "marketplaces": [
                    {
                        "marketplace": {
                            "id": "ATVPDKIKX0DER",
                            "countryCode": "US",
                        }
                    }
                ]
            }
        ),
    )
    db_session.add(connection)
    work = WorkItem(
        workspace_id=workspace.id,
        kind="order_exception",
        source="integration",
        title="Amazon 订单等待发货",
        summary="需要确认物流信息",
        status="waiting_user",
        requires_action="confirm",
        current_step="等待确认发货",
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(connection)
    await db_session.refresh(work)
    return user, workspace, connection, work


@pytest.mark.asyncio
async def test_amazon_order_get_reads_packages_without_pii():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={"order": _order()},
        )

    service = AmazonOrdersService(transport=httpx.MockTransport(handler))
    result = await service.get_order(
        access_token="Atza|access",
        marketplace_id="ATVPDKIKX0DER",
        order_id="111-2222222-3333333",
        included_data=["FULFILLMENT", "PACKAGES"],
    )

    assert result["orderId"] == "111-2222222-3333333"
    assert (
        captured["path"]
        == "/orders/2026-01-01/orders/111-2222222-3333333"
    )
    query = captured["url"].lower()
    assert "includeddata=fulfillment%2cpackages" in query
    assert "buyer" not in query
    assert "recipient" not in query


@pytest.mark.asyncio
async def test_amazon_fulfillment_preflight_execute_and_verify(db_session):
    _user, _workspace, _connection, _work = await _context(
        db_session,
        "amazon-fulfill-adapter@example.com",
    )
    requests: list[dict] = []
    state = {"confirmed": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": (
                    json.loads(request.content)
                    if request.content
                    else None
                ),
            }
        )
        if request.url.path.endswith("/shipmentConfirmation"):
            state["confirmed"] = True
            return httpx.Response(204)
        if request.url.path.endswith("/orders/111-2222222-3333333"):
            packages = (
                [
                    {
                        "packageReferenceId": "1",
                        "carrier": {"code": "UPS"},
                        "trackingNumber": "1Z999",
                        "packageStatus": {"status": "IN_TRANSIT"},
                    }
                ]
                if state["confirmed"]
                else []
            )
            return httpx.Response(
                200,
                json={
                    "order": _order(
                        status=(
                            "SHIPPED" if state["confirmed"] else "UNSHIPPED"
                        ),
                        packages=packages,
                    )
                },
            )
        return httpx.Response(404)

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    try:
        adapter = AmazonOrderFulfillmentActionAdapter(
            db_session,
            user_id=_user.id,
            workspace_id=_workspace.id,
            service=AmazonOrdersService(
                transport=httpx.MockTransport(handler)
            ),
        )
        input_data = {
            "marketplace_id": "ATVPDKIKX0DER",
            "carrier_code": "UPS",
            "tracking_number": "1Z999",
            "ship_date": "2026-11-20T10:00:00Z",
            "package_reference_id": "1",
        }
        before = await adapter.preflight(
            action_id="amazon.orders.fulfill",
            target_id="111-2222222-3333333",
            input_data=input_data,
        )
        assert before["order_status"] == "UNSHIPPED"
        assert before["item_count"] == 2
        assert "private@example.com" not in json.dumps(before)

        execution = await adapter.execute(
            action_id="amazon.orders.fulfill",
            target_id="111-2222222-3333333",
            input_data=input_data,
            idempotency_key="amazon-fulfill:111-2222222-3333333:1Z999",
        )
        confirmation = next(
            item
            for item in requests
            if item["path"].endswith("/shipmentConfirmation")
        )
        assert confirmation["method"] == "POST"
        assert confirmation["body"]["marketplaceId"] == "ATVPDKIKX0DER"
        package = confirmation["body"]["packageDetail"]
        assert package["packageReferenceId"] == "1"
        assert package["carrierCode"] == "UPS"
        assert package["trackingNumber"] == "1Z999"
        assert package["orderItems"] == [
            {"orderItemId": "item-1", "quantity": 2}
        ]

        verification = await adapter.verify(
            action_id="amazon.orders.fulfill",
            target_id="111-2222222-3333333",
            execution=execution,
        )
        assert verification.matched is True
        assert verification.terminal is True
        assert verification.snapshot["tracking_number"] == "1Z999"
        assert "private" not in json.dumps(verification.snapshot).lower()
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_amazon_fulfillment_rejects_fba_and_fully_shipped_order(
    db_session,
):
    user, workspace, _connection, _work = await _context(
        db_session,
        "amazon-fulfill-reject@example.com",
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    try:
        async def fba_handler(request):
            return httpx.Response(
                200,
                json={"order": _order(fulfilled_by="AMAZON")},
            )

        adapter = AmazonOrderFulfillmentActionAdapter(
            db_session,
            user_id=user.id,
            workspace_id=workspace.id,
            service=AmazonOrdersService(
                transport=httpx.MockTransport(fba_handler)
            ),
        )
        with pytest.raises(ValueError, match="FBA"):
            await adapter.preflight(
                action_id="amazon.orders.fulfill",
                target_id="111-2222222-3333333",
                input_data={
                    "marketplace_id": "ATVPDKIKX0DER",
                    "carrier_code": "UPS",
                    "tracking_number": "1Z999",
                },
            )

        async def shipped_handler(request):
            return httpx.Response(
                200,
                json={
                    "order": _order(
                        status="SHIPPED",
                        fulfilled_quantity=2,
                    )
                },
            )

        adapter.service = AmazonOrdersService(
            transport=httpx.MockTransport(shipped_handler)
        )
        with pytest.raises(ValueError, match="当前状态"):
            await adapter.preflight(
                action_id="amazon.orders.fulfill",
                target_id="111-2222222-3333333",
                input_data={
                    "marketplace_id": "ATVPDKIKX0DER",
                    "carrier_code": "UPS",
                    "tracking_number": "1Z999",
                },
            )
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_amazon_fulfillment_requires_carrier_name_for_other(db_session):
    user, workspace, _connection, _work = await _context(
        db_session,
        "amazon-fulfill-carrier@example.com",
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def handler(request):
        return httpx.Response(200, json={"order": _order()})

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    try:
        adapter = AmazonOrderFulfillmentActionAdapter(
            db_session,
            user_id=user.id,
            workspace_id=workspace.id,
            service=AmazonOrdersService(
                transport=httpx.MockTransport(handler)
            ),
        )
        with pytest.raises(ValueError, match="承运商名称"):
            await adapter.preflight(
                action_id="amazon.orders.fulfill",
                target_id="111-2222222-3333333",
                input_data={
                    "marketplace_id": "ATVPDKIKX0DER",
                    "carrier_code": "Others",
                    "tracking_number": "1Z999",
                },
            )
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_amazon_fulfillment_verify_waits_for_tracking_readback(db_session):
    user, workspace, _connection, _work = await _context(
        db_session,
        "amazon-fulfill-verify@example.com",
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "order": _order(
                    status="SHIPPED",
                    fulfilled_quantity=2,
                    packages=[],
                )
            },
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    try:
        adapter = AmazonOrderFulfillmentActionAdapter(
            db_session,
            user_id=user.id,
            workspace_id=workspace.id,
            service=AmazonOrdersService(
                transport=httpx.MockTransport(handler)
            ),
        )
        verification = await adapter.verify(
            action_id="amazon.orders.fulfill",
            target_id="111-2222222-3333333",
            execution=type(
                "Execution",
                (),
                {
                    "output": {
                        "marketplace_id": "ATVPDKIKX0DER",
                        "tracking_number": "1Z999",
                        "package_reference_id": "1",
                    }
                },
            )(),
        )
    finally:
        monkeypatch.undo()

    assert verification.matched is False
    assert verification.details["order_status"] == "SHIPPED"


@pytest.mark.asyncio
async def test_amazon_fulfillment_plan_preview_and_dispatcher(db_session):
    user, workspace, connection, work = await _context(
        db_session,
        "amazon-fulfill-plan@example.com",
    )
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=work.id,
        action_id="amazon.orders.fulfill",
        platform="amazon",
        target_type="order",
        target_id="111-2222222-3333333",
        input_data={
            "marketplace_id": "ATVPDKIKX0DER",
            "carrier_code": "UPS",
            "tracking_number": "1Z999",
            "ship_date": "2026-11-20T10:00:00Z",
            "package_reference_id": "1",
            "item_count": 2,
        },
        idempotency_key="amazon-fulfill-plan-1",
    )
    preview = build_action_preview(run, fallback_title="Amazon 发货")
    adapter = await resolve_action_adapter(db_session, run)

    assert run.status == "awaiting_confirmation"
    assert preview.title == "即将确认 Amazon 发货"
    assert preview.platform == "amazon"
    assert any(
        field.label == "物流单号" and field.value == "1Z999"
        for field in preview.fields
    )
    assert isinstance(adapter, AmazonOrderFulfillmentActionAdapter)
    assert connection.marketplace_id == "ATVPDKIKX0DER"


@pytest.mark.asyncio
async def test_agent_prepares_amazon_fulfillment_without_submitting(
    db_session,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, _connection, _work = await _context(
        db_session,
        "amazon-fulfill-agent@example.com",
    )
    submitted = {"shipment": 0}

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def fake_get_order(self, **kwargs):
        assert kwargs["included_data"] == ["FULFILLMENT"]
        return _order()

    async def fake_confirm_shipment(self, **kwargs):
        submitted["shipment"] += 1

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(AmazonOrdersService, "get_order", fake_get_order)
    monkeypatch.setattr(
        AmazonOrdersService,
        "confirm_shipment",
        fake_confirm_shipment,
    )
    try:
        orchestrator = AgentOrchestrator(
            user,
            db_session,
            workspace_id=workspace.id,
        )
        result = await orchestrator._execute_step(
            "fulfill_amazon_order",
            {
                "order_id": "111-2222222-3333333",
                "marketplace_id": "ATVPDKIKX0DER",
                "carrier_code": "UPS",
                "tracking_number": "1Z999",
                "ship_date": "2026-11-20T10:00:00Z",
                "package_reference_id": "1",
            },
        )
    finally:
        monkeypatch.undo()

    assert submitted["shipment"] == 0
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "amazon.orders.fulfill"
    assert pending["params"]["order_id"] == "111-2222222-3333333"
    assert pending["params"]["tracking_number"] == "1Z999"
