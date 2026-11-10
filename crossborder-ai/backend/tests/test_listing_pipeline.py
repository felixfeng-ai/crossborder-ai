"""Listing pipeline behavior tests.

These tests define the contract before implementation:
1. AI generation persists a ListingDraft and exposes it in product history.
2. Blocked ListingDraft cannot be published.
3. Publish uses ListingDraft content and enforces tenant ownership.
"""

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


async def _create_product(client: AsyncClient, auth_headers: dict, suffix: str = "1") -> str:
    response = await client.post(
        "/api/v1/products/manual",
        json={
            "url": f"https://detail.1688.com/offer/listing-{suffix}.html",
            "title": f"Listing 流水线测试商品 {suffix}",
            "price": 29.9,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["product"]["id"]


def _mock_generate(monkeypatch: pytest.MonkeyPatch, canned: str) -> None:
    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return canned

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)


async def _generate_listing(
    client: AsyncClient,
    auth_headers: dict,
    product_id: str,
) -> dict:
    response = await client.post(
        "/api/v1/content/generate",
        json={
            "product_id": product_id,
            "platform": "amazon",
            "language": "en",
            "tone": "professional",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _make_plan_standard(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    email: str | None = None,
) -> None:
    if email is None:
        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        email = me.json()["email"]
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.plan = "standard"
    await db_session.flush()


@pytest.mark.asyncio
async def test_generation_persists_listing_and_exposes_history(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _mock_generate(monkeypatch, "Premium wireless earbuds with long battery life.")
    product_id = await _create_product(client, auth_headers)

    generated = await _generate_listing(client, auth_headers, product_id)

    assert generated["listing_id"]
    assert generated["listing_status"] == "ready"
    assert generated["compliance_status"] == "pass"

    history = await client.get(
        f"/api/v1/products/{product_id}/listings",
        headers=auth_headers,
    )
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == generated["listing_id"]
    assert items[0]["title"] == generated["title"]
    assert items[0]["compliance_status"] == "pass"


@pytest.mark.asyncio
async def test_blocked_listing_cannot_be_published(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _mock_generate(monkeypatch, "The best seller wireless earbuds with zero risk.")
    product_id = await _create_product(client, auth_headers, suffix="2")
    generated = await _generate_listing(client, auth_headers, product_id)

    assert generated["listing_status"] == "blocked"
    assert generated["compliance_status"] == "block"
    assert generated["blocked"] is True
    await _make_plan_standard(client, auth_headers, db_session)

    response = await client.post(
        "/api/v1/shopify/push",
        json={
            "listing_id": generated["listing_id"],
            "channel_id": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert response.status_code == 409, response.text
    assert "合规" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_uses_listing_content(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _mock_generate(monkeypatch, "Premium wireless earbuds with long battery life.")
    product_id = await _create_product(client, auth_headers, suffix="3")
    generated = await _generate_listing(client, auth_headers, product_id)
    await _make_plan_standard(client, auth_headers, db_session)

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = UUID(me.json()["id"])
    channel = ShopifyChannel(
        user_id=user_id,
        shop_name="listing-pipeline-test",
        shop_domain="listing-pipeline-test.myshopify.com",
        access_token=encrypt_value("shpat_test_token"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()

    captured: dict = {}

    class FakeShopifyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, json=None, headers=None, **kwargs):
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            return httpx.Response(201, json={"product": {"id": 987654}})

    monkeypatch.setattr(shopify_module.httpx, "AsyncClient", FakeShopifyClient)

    response = await client.post(
        "/api/v1/shopify/push",
        json={
            "listing_id": generated["listing_id"],
            "channel_id": str(channel.id),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert captured["payload"]["product"]["title"] == generated["title"]
    assert captured["payload"]["product"]["body_html"] == generated["description"]
    assert response.json()["listing_id"] == generated["listing_id"]


@pytest.mark.asyncio
async def test_other_user_cannot_publish_listing(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _mock_generate(monkeypatch, "Premium wireless earbuds with long battery life.")
    product_id = await _create_product(client, auth_headers, suffix="4")
    generated = await _generate_listing(client, auth_headers, product_id)

    second = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "listing-owner-check@example.com",
            "username": "listing-owner-check",
            "password": "testpass123",
        },
    )
    assert second.status_code == 201, second.text
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    await _make_plan_standard(
        client,
        second_headers,
        db_session,
        email="listing-owner-check@example.com",
    )

    response = await client.post(
        "/api/v1/shopify/push",
        json={
            "listing_id": generated["listing_id"],
            "channel_id": str(uuid.uuid4()),
        },
        headers=second_headers,
    )
    assert response.status_code == 404, response.text
