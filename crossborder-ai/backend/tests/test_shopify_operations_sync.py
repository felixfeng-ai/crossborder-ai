"""Shopify 订单销量与库存同步测试。"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_distribution import (
    MarketingCampaignPublication,
    MarketingPerformanceSnapshot,
)
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.shopify_operations_sync import (
    _next_page_info,
    aggregate_order_sales,
    extract_stock_by_sku,
    sync_shopify_operations,
)
import app.services.shopify_operations_sync as sync_module


def test_aggregate_order_sales_by_sku():
    orders = [
        {
            "line_items": [
                {"sku": "BOX-BLACK", "quantity": 3},
                {"sku": "BOX-WHITE", "quantity": 1},
            ]
        },
        {
            "line_items": [
                {"sku": "BOX-BLACK", "quantity": 2},
                {"sku": "", "quantity": 9},
            ]
        },
        {
            "cancelled_at": "2026-11-01T00:00:00Z",
            "line_items": [{"sku": "BOX-BLACK", "quantity": 100}],
        },
        {
            "financial_status": "refunded",
            "line_items": [{"sku": "BOX-WHITE", "quantity": 100}],
        },
    ]

    assert aggregate_order_sales(orders, days=10) == {
        "BOX-BLACK": 0.5,
        "BOX-WHITE": 0.1,
    }


def test_extract_next_page_info_from_shopify_link_header():
    header = (
        '<https://shop.myshopify.com/admin/api/2024-10/orders.json?limit=250&page_info=abc123>; '
        'rel="next", '
        '<https://shop.myshopify.com/admin/api/2024-10/orders.json?limit=250&page_info=prev>; '
        'rel="previous"'
    )

    assert _next_page_info(header) == "abc123"
    assert _next_page_info("") == ""


def test_extract_stock_by_sku_from_shopify_products():
    products = [
        {
            "id": 1,
            "variants": [
                {"sku": "BOX-BLACK", "inventory_quantity": 12},
                {"sku": "BOX-WHITE", "inventory_quantity": 3},
                {"sku": "", "inventory_quantity": 100},
            ],
        }
    ]

    assert extract_stock_by_sku(products) == {
        "BOX-BLACK": 12,
        "BOX-WHITE": 3,
    }


async def _register_standard(client, db_session, email: str) -> tuple[dict, User]:
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": "testpass123"},
    )
    assert registered.status_code == 201, registered.text
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan = "standard"
    await db_session.flush()
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}, user


@pytest.mark.asyncio
async def test_sync_endpoint_updates_sales_and_stock_without_overwriting_price(
    client,
    db_session,
    monkeypatch,
):
    headers, user = await _register_standard(
        client,
        db_session,
        f"shop-sync-{uuid.uuid4().hex[:8]}@test.com",
    )
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="sync-store",
        shop_domain="sync-store.myshopify.com",
        access_token=encrypt_value("shpat_sync"),
        is_active=True,
    )
    db_session.add(channel)
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Sync Product",
        price=10,
    )
    db_session.add(product)
    await db_session.flush()
    black = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="SYNC-BLACK",
        attributes_json='{"Color":"Black"}',
        price=39.9,
        cost_price=10,
        stock_quantity=99,
        is_active=True,
    )
    white = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="SYNC-WHITE",
        attributes_json='{"Color":"White"}',
        price=42.9,
        cost_price=10,
        stock_quantity=88,
        is_active=True,
    )
    db_session.add_all([black, white])
    await db_session.flush()
    db_session.add(
        Publication(
            user_id=user.id,
            platform="shopify",
            channel_id=str(channel.id),
            status="completed",
            external_product_id="99001",
        )
    )
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="Shopify automatic performance",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="en",
        budget_credits=100,
        brief_json="{}",
    )
    db_session.add(campaign)
    await db_session.flush()
    db_session.add(
        MarketingCampaignPublication(
            user_id=user.id,
            campaign_id=campaign.id,
            platform="shopify",
            channel_id=str(channel.id),
            status="completed",
            external_product_id="99001",
        )
    )
    await db_session.flush()

    requested_urls: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, *, headers=None, params=None, **kwargs):
            requested_urls.append(url)
            if url.endswith("/orders.json"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "orders": [
                            {
                                "id": 7001,
                                "currency": "USD",
                                "line_items": [
                                    {
                                        "sku": "SYNC-BLACK",
                                        "product_id": 99001,
                                        "quantity": 30,
                                        "price": "39.90",
                                    },
                                    {
                                        "sku": "SYNC-WHITE",
                                        "product_id": 99001,
                                        "quantity": 6,
                                        "price": "42.90",
                                    },
                                ]
                            }
                        ]
                    },
                )
            if url.endswith("/products.json"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "products": [
                            {
                                "id": 99001,
                                "variants": [
                                    {"sku": "SYNC-BLACK", "inventory_quantity": 7},
                                    {"sku": "SYNC-WHITE", "inventory_quantity": 4},
                                ],
                            }
                        ]
                    },
                )
            return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(sync_module.httpx, "AsyncClient", FakeClient)
    direct = await sync_shopify_operations(
        db_session,
        user=user,
        channel=channel,
        days=30,
    )
    assert direct["orders_scanned"] == 1
    assert direct["products_scanned"] == 1

    response = await client.post(
        "/api/v1/shopify/sync-operations",
        params={"channel_id": str(channel.id), "days": 30},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["sales_rate_updates"] == 2
    assert response.json()["stock_updates"] == 2
    assert response.json()["campaign_performance_updates"] == 1
    assert all("/admin/api/2026-10/" in url for url in requested_urls)
    await db_session.refresh(black)
    await db_session.refresh(white)
    assert black.daily_sales_rate == 1.0
    assert white.daily_sales_rate == 0.2
    assert black.stock_quantity == 7
    assert white.stock_quantity == 4
    assert black.price == 39.9
    assert white.price == 42.9
    snapshots = (
        await db_session.execute(
            select(MarketingPerformanceSnapshot).where(
                MarketingPerformanceSnapshot.campaign_id == campaign.id,
                MarketingPerformanceSnapshot.source == "shopify_orders",
            )
        )
    ).scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].orders == 1
    assert snapshots[0].revenue == 1454.4


@pytest.mark.asyncio
async def test_sync_rejects_foreign_channel(client, db_session):
    headers, _ = await _register_standard(
        client,
        db_session,
        f"shop-sync-owner-{uuid.uuid4().hex[:8]}@test.com",
    )
    owner = User(
        email=f"shop-sync-foreign-{uuid.uuid4().hex[:8]}@test.com",
        username="shop-sync-foreign",
        password_hash="x",
        plan="standard",
    )
    db_session.add(owner)
    await db_session.flush()
    channel = ShopifyChannel(
        user_id=owner.id,
        shop_name="foreign-sync",
        shop_domain="foreign-sync.myshopify.com",
        access_token=encrypt_value("shpat_foreign"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()

    response = await client.post(
        "/api/v1/shopify/sync-operations",
        params={"channel_id": str(channel.id), "days": 30},
        headers=headers,
    )

    assert response.status_code == 404
