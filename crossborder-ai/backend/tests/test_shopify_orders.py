"""Shopify 订单接口错误语义测试。"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
import app.routers.shopify as shopify_module


class _ProtectedCustomerDataResponse:
    status_code = 403
    text = json.dumps(
        {
            "errors": (
                "[API] This app is not approved to access REST endpoints "
                "with protected customer data."
            )
        }
    )

    def json(self) -> dict:
        return json.loads(self.text)


class _ProtectedCustomerDataClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return _ProtectedCustomerDataResponse()


@pytest.mark.asyncio
async def test_shopify_orders_maps_protected_customer_data_error(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="permission-store",
        shop_domain="permission-store.myshopify.com",
        access_token=encrypt_value("shpat_test"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()
    monkeypatch.setattr(
        shopify_module.httpx,
        "AsyncClient",
        _ProtectedCustomerDataClient,
    )

    response = await client.get(
        "/api/v1/shopify/orders",
        params={"channel_id": str(channel.id)},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "受保护客户数据" in response.json()["detail"]
    assert "protected customer data" not in response.json()["detail"]
