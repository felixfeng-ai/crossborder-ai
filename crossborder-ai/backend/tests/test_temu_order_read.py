"""Temu LOCAL/SEMI 订单只读测试。"""

import json

import httpx
import pytest

from app.core.crypto import encrypt_value
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services import provider_config
from app.services.temu_open_api import TemuOpenApiService
from app.services.temu_order_read import TemuOrderReadService


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _page_item():
    return {
        "parentOrderMap": {
            "parentOrderSn": "PO-1001",
            "parentOrderStatus": 2,
            "parentOrderTime": 1763700000,
            "updateTime": 1763700100,
            "expectShipLatestTime": 1763800000,
            "fulfillmentWarning": ["soon_to_be_overdue"],
            "parentOrderLabel": [{"name": "Urgent", "value": 1}],
            "buyerPaidShippingAmount": {
                "currency": "USD",
                "amount": 4.99,
            },
        },
        "orderList": [
            {
                "orderSn": "SO-1001",
                "orderStatus": 2,
                "goodsId": 2001,
                "goodsName": "Temu Product",
                "skuId": 3001,
                "quantity": 2,
                "spec": "Black",
                "fulfillmentType": "fulfillBySeller",
                "packageAbnormalTypeList": ["NO_TRACK"],
                "orderCreateTime": 1763700000,
                "orderShippingTime": 0,
                "inventoryDeductionWarehouseId": "WH-1",
                "inventoryDeductionWarehouseName": "Main Warehouse",
                "buyerName": "Private Buyer",
                "shippingAddress": "private street",
            }
        ],
    }


async def _connection(db_session, email: str, store_type: str, scopes: list[str]):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Store",
        external_account_id="1001",
        marketplace_id="us",
        credentials=encrypt_value(
            json.dumps({"access_token": "temu-token"})
        ),
        status="active",
        metadata_json=json.dumps(
            {"store_type": store_type, "api_scope_list": scopes}
        ),
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)
    return user, connection


@pytest.mark.asyncio
async def test_temu_local_order_read_and_normalization(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure(monkeypatch)
    user, connection = await _connection(
        db_session,
        "temu-order-read@example.com",
        "local",
        ["bg.order.list.v2.get"],
    )
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "errorCode": 1000000,
                "result": {
                    "pageItems": [_page_item()],
                    "totalItemNum": 1,
                },
            },
        )

    service = TemuOrderReadService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    result = await service.list_orders(
        connection_id=connection.id,
        page_number=1,
        page_size=20,
        parent_order_status=2,
    )

    assert captured["body"]["type"] == "bg.order.list.v2.get"
    assert captured["body"]["pageNumber"] == 1
    assert captured["body"]["parentOrderStatus"] == 2
    assert result["items"][0]["parent_order_sn"] == "PO-1001"
    assert result["items"][0]["orders"][0]["sku_id"] == "3001"
    response_text = json.dumps(result).lower()
    assert "private buyer" not in response_text
    assert "private street" not in response_text
    assert "access_token" not in response_text


@pytest.mark.asyncio
async def test_temu_order_read_rejects_crossborder_or_missing_scope(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure(monkeypatch)
    user, local = await _connection(
        db_session,
        "temu-order-invalid@example.com",
        "local",
        [],
    )
    crossborder = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Crossborder",
        external_account_id="1002",
        marketplace_id="global",
        credentials=encrypt_value('{"access_token":"temu-token"}'),
        status="active",
        metadata_json=(
            '{"store_type":"crossborder",'
            '"api_scope_list":["bg.order.list.v2.get"]}'
        ),
    )
    db_session.add(crossborder)
    await db_session.commit()
    await db_session.refresh(crossborder)
    service = TemuOrderReadService(db_session, user_id=user.id)

    with pytest.raises(ValueError, match="权限"):
        await service.list_orders(connection_id=local.id)
    with pytest.raises(ValueError, match="店铺类型"):
        await service.list_orders(connection_id=crossborder.id)


@pytest.mark.asyncio
async def test_agent_queries_temu_orders_without_sensitive_fields(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, connection = await _connection(
        db_session,
        "temu-order-agent@example.com",
        "local",
        ["bg.order.list.v2.get"],
    )
    captured = {}

    async def fake_list(self, **kwargs):
        captured.update(kwargs)
        return {
            "connection_id": str(connection.id),
            "store_type": "local",
            "page_number": 1,
            "total": 1,
            "items": [
                {
                    "parent_order_sn": "PO-1001",
                    "parent_order_status": 2,
                    "orders": [
                        {
                            "order_sn": "SO-1001",
                            "goods_id": "2001",
                            "goods_name": "Temu Product",
                            "sku_id": "3001",
                            "quantity": 2,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.ai.agent_orchestrator."
        "TemuOrderReadService.list_orders",
        fake_list,
    )
    orchestrator = AgentOrchestrator(user, db_session)
    result = await orchestrator._execute_step(
        "search_temu_orders",
        {
            "connection_id": str(connection.id),
            "page_number": 1,
            "page_size": 20,
            "parent_order_status": 2,
        },
    )

    assert result["status"] == "success"
    assert result["data"]["items"][0]["parent_order_sn"] == "PO-1001"
    assert captured["connection_id"] == connection.id
    assert captured["parent_order_status"] == 2
    response_text = json.dumps(result, ensure_ascii=False).lower()
    assert "access_token" not in response_text
    assert "private buyer" not in response_text
    assert "private street" not in response_text


@pytest.mark.asyncio
async def test_agent_requires_temu_connection_when_multiple_stores(
    db_session,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, _first = await _connection(
        db_session,
        "temu-order-multiple@example.com",
        "local",
        ["bg.order.list.v2.get"],
    )
    second = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Semi Store",
        external_account_id="1002",
        marketplace_id="eu",
        credentials=encrypt_value('{"access_token":"temu-token-2"}'),
        status="active",
        metadata_json=(
            '{"store_type":"semi",'
            '"api_scope_list":["bg.order.list.v2.get"]}'
        ),
    )
    db_session.add(second)
    await db_session.commit()

    orchestrator = AgentOrchestrator(user, db_session)
    result = await orchestrator._execute_step("search_temu_orders", {})

    assert result["status"] == "needs_input"
    assert len(result["data"]["connections"]) == 2
    assert "access_token" not in json.dumps(result).lower()


def test_agent_registers_temu_order_read_tool():
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "search_temu_orders" in names
