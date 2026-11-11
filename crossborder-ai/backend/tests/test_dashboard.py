"""VeyaShip - 看板测试（F1 Dashboard）

覆盖：dashboard 统计接口（GET /api/v1/analytics/dashboard）。

注：listings/content/platforms 字段与 /usage-trend 接口在当前系统从未实现
（app/api/v1/endpoints/ 下有未挂载的旧 schema 版本），对应过时测试已删除。
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from httpx import AsyncClient

from app.models.listing_draft import ListingDraft
from app.models.operation_alert import OperationAlert
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.dashboard_service import build_dashboard_data
from app.services.listing_service import persist_generated_listing
from app.services.store_check_service import run_store_check as execute_store_check


@pytest.mark.asyncio
async def test_dashboard_product_count(client: AsyncClient, auth_headers: dict):
    """测试看板商品计数

    创建 2 个商品后，dashboard 的商品数应为 2。
    """
    # 创建 2 个商品
    for i in range(2):
        await client.post(
            "/api/v1/products/manual",
            json={
                "url": f"https://detail.1688.com/offer/{300000 + i}.html",
                "title": f"看板商品{i}",
            },
            headers=auth_headers,
        )

    # 查看 dashboard 统计
    response = await client.get("/api/v1/analytics/dashboard", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["products"]["total"] == 2


@pytest.mark.asyncio
async def test_dashboard_unauthorized(client: AsyncClient):
    """测试未认证时返回 401"""
    response = await client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_returns_live_pipeline_and_operating_priorities(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    incomplete = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/dashboard-incomplete.html",
        title="未完成商品链路",
        price=12.5,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(incomplete)
    await db_session.flush()
    ready_product = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/dashboard-ready.html",
        title="待配置售价商品",
        price=18.0,
        main_image_url="https://cdn.example.com/dashboard-ready.jpg",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(ready_product)
    await db_session.flush()
    await persist_generated_listing(
        db_session,
        user=user,
        product=ready_product,
        platform="shopify",
        language="en",
        tone="professional",
        title="Dashboard Ready Listing",
        description="Listing description",
        bullet_points=["One", "Two", "Three"],
        seo_title="Dashboard Listing",
        seo_description="Dashboard listing description",
        violations=[],
        blocked=False,
        ai_model_used="test",
    )
    db_session.add(
        ProductVariant(
            user_id=user.id,
            product_id=ready_product.id,
            sku="DASH-NO-PRICE",
            attributes_json='{"Color":"Black"}',
            price=None,
            cost_price=18,
            stock_quantity=12,
            is_active=True,
        )
    )
    await db_session.flush()

    direct = await build_dashboard_data(db_session, user)

    response = await client.get("/api/v1/analytics/dashboard", headers=auth_headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["products"]["total"] == 2
    pipeline = data["pipeline"]
    assert pipeline["product"]["id"] == str(ready_product.id)
    stages = {item["id"]: item for item in pipeline["stages"]}
    assert stages["product"]["status"] == "completed"
    assert stages["listing"]["status"] == "completed"
    assert stages["media"]["status"] == "completed"
    assert stages["sku"]["status"] in {"current", "blocked"}
    assert "售价" in stages["sku"]["detail"]
    assert stages["channel"]["status"] == "pending"
    assert pipeline["next_action"]["stage"] == "sku"
    assert pipeline["next_action"]["href"].startswith("/app/catalog")

    facts = {item["id"]: item for item in data["facts"]}
    assert facts["content"]["value"] >= 1
    assert facts["media"]["value"] >= 1
    assert facts["sku"]["value"] >= 2
    assert all("href" in item for item in facts.values())
    assert data["recent_operations"]
    assert direct["pipeline"]["next_action"]["stage"] == "sku"
    assert direct["facts"][0]["id"] == "content"


@pytest.mark.asyncio
async def test_store_check_covers_listing_sku_and_returns_actionable_history(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    product = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/store-check-full.html",
        title="基础字段完整但链路未完成",
        price=18,
        main_image_url="https://cdn.example.com/store-check.jpg",
    )
    db_session.add(product)
    await db_session.flush()

    direct = await execute_store_check(
        db_session,
        user,
        persist_log=False,
    )
    assert direct["issue_count"] == 1
    assert {"missing_listing", "missing_active_sku"} <= {
        item["code"] for item in direct["issues"][0]["issues"]
    }

    response = await client.post("/api/v1/analytics/store-check", headers=auth_headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["issue_count"] == 1
    assert data["healthy"] == 0
    issue = data["issues"][0]
    codes = {item["code"] for item in issue["issues"]}
    assert {"missing_listing", "missing_active_sku"} <= codes
    assert issue["severity"] in {"warning", "critical"}
    assert issue["action_href"].startswith(f"/app/products/{product.id}")

    history = await client.get(
        "/api/v1/analytics/store-check-history",
        headers=auth_headers,
    )
    assert history.status_code == 200
    latest = history.json()["items"][0]
    assert latest["issues"][0]["action_href"] == issue["action_href"]
    assert latest["checked_scopes"] == [
        "basic",
        "listing",
        "media",
        "sku",
        "publication",
        "operations",
    ]


@pytest.mark.asyncio
async def test_store_check_aggregates_blocked_listing_and_sku_risks(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    product = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/store-check-risk.html",
        title="高风险商品",
        price=20,
        main_image_url="https://cdn.example.com/risk.jpg",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ListingDraft(
            user_id=user.id,
            product_id=product.id,
            platform="amazon",
            title="Blocked Listing",
            description="Description",
            bullet_points="[]",
            version=1,
            content_hash="r" * 64,
            compliance_status="block",
            compliance_violations='["违规词"]',
            status="blocked",
        )
    )
    db_session.add(
        ProductVariant(
            user_id=user.id,
            product_id=product.id,
            sku="RISK-SKU",
            attributes_json='{"Color":"Black"}',
            price=None,
            cost_price=20,
            stock_quantity=0,
            is_active=True,
        )
    )
    db_session.add(
        OperationAlert(
            user_id=user.id,
            product_id=product.id,
            alert_type="out_of_stock",
            severity="critical",
            title="库存告急",
            message="库存为 0",
            details_json="{}",
            status="open",
        )
    )
    await db_session.flush()

    result = await execute_store_check(
        db_session,
        user,
        persist_log=False,
    )

    issue = result["issues"][0]
    codes = {item["code"] for item in issue["issues"]}
    assert {
        "listing_blocked",
        "sku_missing_price",
        "sku_out_of_stock",
        "open_operation_alert",
    } <= codes
    assert issue["severity"] == "critical"


