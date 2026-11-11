"""运营监控、补货模型和预警。"""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.listing_draft import ListingDraft
from app.models.operation_alert import OperationAlert
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.models.variant_snapshot import VariantSnapshot
from app.services.operations_monitor import (
    calculate_margin,
    calculate_replenishment,
)


async def _seed_operation_sku(
    db_session,
    *,
    stock: int = 20,
    daily_sales: float = 2,
    price: float = 30,
    cost: float = 20,
) -> tuple[Product, ProductVariant]:
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/ops-{uuid.uuid4().hex}.html",
        title="Operations Bottle",
        price=cost,
    )
    db_session.add(product)
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku=f"OPS-{uuid.uuid4().hex[:6]}",
        price=price,
        cost_price=cost,
        stock_quantity=stock,
        daily_sales_rate=daily_sales,
        is_active=True,
    )
    db_session.add(variant)
    await db_session.flush()
    return product, variant


def test_replenishment_and_margin_math():
    replenishment = calculate_replenishment(
        stock_quantity=20,
        daily_sales_rate=2,
        lead_time_days=14,
        safety_stock_days=3,
    )
    margin = calculate_margin(
        selling_price=40,
        cost_price=20,
        platform_fee_rate=0.15,
        shipping_cost=3,
    )

    assert replenishment["days_cover"] == 10
    assert replenishment["reorder_point"] == 34
    assert replenishment["suggested_quantity"] == 14
    assert replenishment["status"] == "reorder"
    assert margin["net_profit"] == 11
    assert margin["margin_rate"] == 27.5


def test_replenishment_without_sales_data_is_unknown():
    result = calculate_replenishment(
        stock_quantity=20,
        daily_sales_rate=0,
        lead_time_days=14,
        safety_stock_days=3,
    )

    assert result["days_cover"] is None
    assert result["reorder_point"] is None
    assert result["suggested_quantity"] == 0
    assert result["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_scan_creates_snapshots_and_alerts(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    product, variant = await _seed_operation_sku(db_session, stock=4, daily_sales=2)

    response = await client.post("/api/v1/operations/scan", headers=auth_headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sku_count"] == 1
    assert data["open_alerts"] >= 2

    snapshots = (
        await db_session.execute(
            select(VariantSnapshot).where(VariantSnapshot.variant_id == variant.id)
        )
    ).scalars().all()
    alerts = (
        await db_session.execute(
            select(OperationAlert).where(OperationAlert.user_id == variant.user_id)
        )
    ).scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].stock_quantity == 4
    assert any(item.alert_type == "low_stock" for item in alerts)
    assert any(item.alert_type == "low_margin" for item in alerts)
    assert product.id == variant.product_id


@pytest.mark.asyncio
async def test_repeated_scan_deduplicates_and_resolves_recovered_alert(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    _, variant = await _seed_operation_sku(db_session, stock=4, daily_sales=2)

    await client.post("/api/v1/operations/scan", headers=auth_headers)
    await client.post("/api/v1/operations/scan", headers=auth_headers)
    open_alerts = (
        await db_session.execute(
            select(OperationAlert).where(
                OperationAlert.variant_id == variant.id,
                OperationAlert.alert_type == "low_stock",
                OperationAlert.status == "open",
            )
        )
    ).scalars().all()
    assert len(open_alerts) == 1

    variant.stock_quantity = 100
    await db_session.flush()
    await client.post("/api/v1/operations/scan", headers=auth_headers)

    recovered = (
        await db_session.execute(
            select(OperationAlert).where(
                OperationAlert.variant_id == variant.id,
                OperationAlert.alert_type == "low_stock",
            )
        )
    ).scalars().all()
    assert len(recovered) == 1
    assert recovered[0].status == "resolved"


@pytest.mark.asyncio
async def test_alert_acknowledgement_and_user_isolation(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    _, variant = await _seed_operation_sku(db_session, stock=0, daily_sales=2)
    await client.post("/api/v1/operations/scan", headers=auth_headers)
    alert = (
        await db_session.execute(
            select(OperationAlert).where(OperationAlert.variant_id == variant.id)
        )
    ).scalars().first()
    assert alert is not None

    acknowledged = await client.patch(
        f"/api/v1/operations/alerts/{alert.id}",
        json={"status": "acknowledged"},
        headers=auth_headers,
    )
    assert acknowledged.status_code == 200
    await db_session.refresh(alert)
    assert alert.status == "acknowledged"

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ops-other-{uuid.uuid4().hex[:6]}@example.com",
            "username": "ops-other",
            "password": "testpass123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    forbidden = await client.patch(
        f"/api/v1/operations/alerts/{alert.id}",
        json={"status": "acknowledged"},
        headers=other_headers,
    )
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_monitor_settings_and_daily_sales_rate(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    _, variant = await _seed_operation_sku(db_session, daily_sales=0)

    settings_response = await client.put(
        "/api/v1/operations/settings",
        json={
            "target_margin_rate": 35,
            "low_stock_days": 10,
            "lead_time_days": 21,
            "safety_stock_days": 5,
            "platform_fee_rate": 0.18,
            "shipping_cost": 4.5,
        },
        headers=auth_headers,
    )
    assert settings_response.status_code == 200, settings_response.text
    assert settings_response.json()["target_margin_rate"] == 35

    rate_response = await client.patch(
        f"/api/v1/operations/variants/{variant.id}/sales-rate",
        json={"daily_sales_rate": 3.5},
        headers=auth_headers,
    )
    assert rate_response.status_code == 200, rate_response.text
    await db_session.refresh(variant)
    assert variant.daily_sales_rate == 3.5

    overview = await client.get("/api/v1/operations/overview", headers=auth_headers)
    assert overview.status_code == 200
    assert overview.json()["settings"]["lead_time_days"] == 21


@pytest.mark.asyncio
async def test_scan_reports_listing_blocked(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    product, _ = await _seed_operation_sku(db_session)
    db_session.add(
        ListingDraft(
            user_id=product.user_id,
            product_id=product.id,
            platform="amazon",
            title="Blocked Listing",
            description="Description",
            bullet_points=json.dumps(["One", "Two", "Three", "Four", "Five"]),
            version=1,
            content_hash=uuid.uuid4().hex,
            compliance_status="block",
            compliance_violations='["违规词"]',
            status="blocked",
        )
    )
    await db_session.flush()

    response = await client.post("/api/v1/operations/scan", headers=auth_headers)
    assert response.status_code == 200
    alerts = await client.get(
        "/api/v1/operations/alerts",
        headers=auth_headers,
    )
    assert any(
        item["alert_type"] == "listing_blocked"
        for item in alerts.json()["items"]
    )


@pytest.mark.asyncio
async def test_refresh_supplier_cost_updates_product_and_missing_variant_cost(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    product, variant = await _seed_operation_sku(db_session)
    variant.cost_price = None
    variant.price = 42
    await db_session.flush()

    async def fake_scrape(url, **kwargs):
        assert url == product.url
        return {"price": 18.8, "title": product.title}

    monkeypatch.setattr(
        "app.services.operations_monitor.scrape_1688",
        fake_scrape,
    )

    response = await client.post(
        "/api/v1/operations/refresh-costs",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["refreshed"] == 1
    await db_session.refresh(product)
    await db_session.refresh(variant)
    assert product.price == 18.8
    assert variant.cost_price == 18.8
