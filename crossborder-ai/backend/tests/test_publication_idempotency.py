"""统一平台发布记录与幂等行为测试。"""

import uuid
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.routers import shopify as shopify_module
from app.services.ai.deepseek import DeepSeekService


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": "testpass123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_standard(db_session, email: str) -> None:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan = "standard"
    await db_session.flush()


async def _create_listing(
    client: AsyncClient,
    headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str]:
    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "Premium wireless earbuds with long battery life."

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    product = await client.post(
        "/api/v1/products/manual",
        json={
            "url": f"https://detail.1688.com/offer/pub-{uuid.uuid4().hex}.html",
            "title": "发布幂等测试商品",
            "price": 29.9,
        },
        headers=headers,
    )
    assert product.status_code == 201, product.text
    listing = await client.post(
        "/api/v1/content/generate",
        json={"product_id": product.json()["product"]["id"], "platform": "amazon"},
        headers=headers,
    )
    assert listing.status_code == 200, listing.text
    return product.json()["product"]["id"], listing.json()["listing_id"]


@pytest.mark.asyncio
async def test_shopify_publish_is_idempotent_by_header(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    email = "publication-idempotency@example.com"
    headers = await _register(client, email)
    await _make_standard(db_session, email)
    _, listing_id = await _create_listing(client, headers, monkeypatch)

    me = await client.get("/api/v1/auth/me", headers=headers)
    channel = ShopifyChannel(
        user_id=UUID(me.json()["id"]),
        shop_name="publish-idempotency-test",
        shop_domain="publish-idempotency-test.myshopify.com",
        access_token=encrypt_value("shpat_test"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()

    calls = 0

    class FakeShopifyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return httpx.Response(
                201,
                request=httpx.Request("POST", "https://shop.example/products.json"),
                json={"product": {"id": 123456}},
            )

    monkeypatch.setattr(shopify_module.httpx, "AsyncClient", FakeShopifyClient)
    request_body = {"listing_id": listing_id, "channel_id": str(channel.id)}
    idem_headers = {**headers, "Idempotency-Key": "publish-once-001"}

    first = await client.post(
        "/api/v1/shopify/push",
        json=request_body,
        headers=idem_headers,
    )
    second = await client.post(
        "/api/v1/shopify/push",
        json=request_body,
        headers=idem_headers,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["publication_id"] == second.json()["publication_id"]
    assert first.json()["shopify_product_id"] == second.json()["shopify_product_id"]
    assert calls == 1


@pytest.mark.asyncio
async def test_platform_capabilities_are_explicit(client: AsyncClient):
    response = await client.get("/api/v1/platforms/capabilities")
    assert response.status_code == 200, response.text
    platforms = response.json()["platforms"]
    assert platforms["shopify"]["publish_supported"] is True
    assert platforms["amazon"]["auth_supported"] is True
    assert platforms["amazon"]["publish_supported"] is False
    assert platforms["temu"]["publish_supported"] is False
    assert platforms["shein"]["publish_supported"] is False
