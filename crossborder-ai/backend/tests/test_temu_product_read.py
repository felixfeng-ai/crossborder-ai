"""Temu 商品只读权限、网关请求和归一化测试。"""

import json
import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import decrypt_value, encrypt_value
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services import provider_config
from app.services.temu_open_api import TemuOpenApiService
from app.services.temu_product_read import TemuProductReadService


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


def _goods():
    return {
        "goodsId": 1001,
        "outGoodsSn": "OUT-1001",
        "goodsName": "Test Temu Product",
        "status4VO": 1,
        "subStatus4VO": 2,
        "goodsStatusChangeTime": "2026-11-20T10:00:00Z",
        "price": "19.90",
        "marketPrice": 21,
        "currency": "USD",
        "retailPrice": {"amount": "20.50", "currency": "USD"},
        "listPrice": {"amount": "25.00", "currency": "USD"},
        "thumbUrl": "https://cdn.temu.example/product.jpg",
        "skuInfoList": [
            {
                "skuId": 2001,
                "skuSn": "SKU-1001",
                "stock": 12,
                "specList": [
                    {
                        "parentSpecName": "Color",
                        "specName": "Black",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_temu_product_read_uses_scope_and_signed_post(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
):
    _configure_temu(monkeypatch)
    user = User(
        email="temu-product-read@example.com",
        username="temu-product-read",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Local US",
        external_account_id="1001",
        marketplace_id="us",
        credentials=encrypt_value(
            json.dumps({"access_token": "temu-access-token"})
        ),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "local",
                "api_scope_list": ["bg.local.goods.list.query"],
            }
        ),
    )
    db_session.add(connection)
    await db_session.commit()
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "success": True,
                "errorCode": 1000000,
                "result": {
                    "goodsList": [_goods()],
                    "pageNo": 1,
                    "total": 1,
                },
            },
        )

    service = TemuProductReadService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    result = await service.list_products(
        connection_id=connection.id,
        page_no=1,
        page_size=20,
    )

    assert captured["url"] == (
        "https://openapi-b-us.temu.com/openapi/router"
    )
    assert captured["body"]["type"] == "bg.local.goods.list.query"
    assert captured["body"]["pageNo"] == 1
    assert captured["body"]["pageSize"] == 20
    assert captured["body"]["app_key"] == "temu-app-key"
    item = result["items"][0]
    assert item["goods_id"] == "1001"
    assert item["price"] == "19.90"
    assert item["skus"][0]["stock"] == 12
    assert "access_token" not in json.dumps(result).lower()


@pytest.mark.asyncio
async def test_temu_product_read_rejects_missing_scope_or_crossborder(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
):
    _configure_temu(monkeypatch)
    user = User(
        email="temu-product-invalid@example.com",
        username="temu-product-invalid",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    missing = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu No Scope",
        external_account_id="1002",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"token"}'),
        status="active",
        metadata_json='{"store_type":"local","api_scope_list":[]}',
    )
    crossborder = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Crossborder",
        external_account_id="1003",
        marketplace_id="global",
        credentials=encrypt_value('{"access_token":"token"}'),
        status="active",
        metadata_json=(
            '{"store_type":"crossborder",'
            '"api_scope_list":["bg.local.goods.list.query"]}'
        ),
    )
    db_session.add_all([missing, crossborder])
    await db_session.commit()
    service = TemuProductReadService(db_session, user_id=user.id)

    with pytest.raises(ValueError, match="权限"):
        await service.list_products(connection_id=missing.id)
    with pytest.raises(ValueError, match="店铺类型"):
        await service.list_products(connection_id=crossborder.id)


async def _register(client: AsyncClient, db_session, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@", 1)[0],
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    return headers, user


@pytest.mark.asyncio
async def test_temu_product_endpoint_does_not_leak_credentials(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    headers, user = await _register(
        client,
        db_session,
        "temu-product-endpoint@example.com",
    )
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Endpoint",
        external_account_id="1004",
        marketplace_id="us",
        credentials=encrypt_value(
            json.dumps({"access_token": "endpoint-secret-token"})
        ),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "local",
                "api_scope_list": ["bg.local.goods.list.query"],
            }
        ),
    )
    db_session.add(connection)
    await db_session.commit()

    from app.routers import platforms as platforms_module

    async def fake_list(self, **kwargs):
        return {"items": [], "page_no": 1, "total": 0}

    monkeypatch.setattr(
        platforms_module.TemuProductReadService,
        "list_products",
        fake_list,
    )
    response = await client.get(
        f"/api/v1/platforms/temu/{connection.id}/products",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "endpoint-secret-token" not in response.text
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_agent_queries_temu_products(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    _configure_temu(monkeypatch)
    user = User(
        email="temu-product-agent@example.com",
        username="temu-product-agent",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Agent Store",
        external_account_id="1005",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"agent-token"}'),
        status="active",
        metadata_json=(
            '{"store_type":"local",'
            '"api_scope_list":["bg.local.goods.list.query"]}'
        ),
    )
    db_session.add(connection)
    await db_session.commit()

    async def fake_list(self, **kwargs):
        return {
            "items": [
                {
                    "goods_id": "1001",
                    "name": "Agent Product",
                    "skus": [{"sku_id": "1", "stock": 12}],
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr(
        "app.services.ai.agent_orchestrator.TemuProductReadService.list_products",
        fake_list,
    )
    orchestrator = AgentOrchestrator(user, db_session)
    result = await orchestrator._execute_step(
        "search_temu_products",
        {"connection_id": str(connection.id), "page_size": 20},
    )
    assert result["status"] == "success"
    assert result["data"]["items"][0]["goods_id"] == "1001"
