"""Shopify 强制隐私 Webhook 行为测试。"""

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import func, select

import app.routers.shopify as shopify_router
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.shopify_compliance_event import ShopifyComplianceEvent
from app.models.user import User


WEBHOOK_SECRET = "shopify-webhook-test-secret"


def _signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def shopify_webhook_secret(monkeypatch):
    monkeypatch.setattr(shopify_router.settings, "SHOPIFY_API_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(
        shopify_router.provider_config,
        "get",
        lambda group, key, default="": (
            WEBHOOK_SECRET
            if group == "shopify" and key == "api_secret"
            else default
        ),
    )


def _headers(topic: str, payload: bytes, *, webhook_id: str | None = None, signature: str | None = None):
    return {
        "Content-Type": "application/json",
        "X-Shopify-Hmac-Sha256": signature or _signature(payload),
        "X-Shopify-Topic": topic,
        "X-Shopify-Shop-Domain": "compliance-test.myshopify.com",
        "X-Shopify-Webhook-Id": webhook_id or str(uuid.uuid4()),
    }


@pytest.mark.asyncio
async def test_customer_data_request_is_verified_and_audited_without_pii(
    client,
    db_session,
):
    payload = json.dumps(
        {
            "shop_id": 1001,
            "shop_domain": "compliance-test.myshopify.com",
            "customer": {"id": 99, "email": "private@example.com"},
            "orders_requested": [123],
        }
    ).encode()

    response = await client.post(
        "/api/v1/shopify/webhooks/customers/data_request",
        content=payload,
        headers=_headers("customers/data_request", payload),
    )

    assert response.status_code == 200, response.text
    event = (
        await db_session.execute(select(ShopifyComplianceEvent))
    ).scalar_one()
    assert event.topic == "customers/data_request"
    assert event.status == "processed"
    assert "private@example.com" not in (event.action_summary or "")
    assert "99" not in (event.action_summary or "")


@pytest.mark.asyncio
async def test_invalid_webhook_signature_is_rejected_without_event(client, db_session):
    payload = b'{"shop_id":1001}'
    response = await client.post(
        "/api/v1/shopify/webhooks/customers/redact",
        content=payload,
        headers=_headers(
            "customers/redact",
            payload,
            signature="0" * 64,
        ),
    )

    assert response.status_code == 401
    count = (
        await db_session.execute(select(func.count()).select_from(ShopifyComplianceEvent))
    ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_duplicate_webhook_delivery_is_idempotent(client, db_session):
    payload = b'{"shop_id":1001}'
    webhook_id = str(uuid.uuid4())
    headers = _headers("customers/redact", payload, webhook_id=webhook_id)

    first = await client.post(
        "/api/v1/shopify/webhooks/customers/redact",
        content=payload,
        headers=headers,
    )
    second = await client.post(
        "/api/v1/shopify/webhooks/customers/redact",
        content=payload,
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    count = (
        await db_session.execute(select(func.count()).select_from(ShopifyComplianceEvent))
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_shop_redact_deletes_channel_and_publications(client, db_session):
    user = User(
        email=f"redact-{uuid.uuid4().hex[:8]}@example.com",
        username="redact-user",
        password_hash="x",
    )
    db_session.add(user)
    await db_session.flush()
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="compliance-test",
        shop_domain="compliance-test.myshopify.com",
        access_token="enc:test",
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()
    publication = Publication(
        user_id=user.id,
        platform="shopify",
        channel_id=str(channel.id),
        status="completed",
        external_product_id="123",
    )
    db_session.add(publication)
    await db_session.flush()

    payload = json.dumps(
        {
            "shop_id": 1001,
            "shop_domain": "compliance-test.myshopify.com",
        }
    ).encode()
    response = await client.post(
        "/api/v1/shopify/webhooks/shop/redact",
        content=payload,
        headers=_headers("shop/redact", payload),
    )

    assert response.status_code == 200, response.text
    assert (
        await db_session.execute(
            select(ShopifyChannel).where(ShopifyChannel.id == channel.id)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(Publication).where(Publication.id == publication.id)
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_webhook_fails_closed_without_secret(client, db_session, monkeypatch):
    monkeypatch.setattr(shopify_router.settings, "SHOPIFY_API_SECRET", "")
    monkeypatch.setattr(
        shopify_router.provider_config,
        "get",
        lambda group, key, default="": default,
    )
    payload = b'{"shop_id":1001}'

    response = await client.post(
        "/api/v1/shopify/webhooks/customers/data_request",
        content=payload,
        headers=_headers("customers/data_request", payload),
    )

    assert response.status_code == 503
    count = (
        await db_session.execute(select(func.count()).select_from(ShopifyComplianceEvent))
    ).scalar_one()
    assert count == 0
