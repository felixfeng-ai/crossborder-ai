"""效果驱动 A/B 优化与自动暂停测试。"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import MarketingPerformanceSnapshot
from app.models.product import Product
from app.models.user import User
from app.services.marketing_optimization import evaluate_variant_performance


def _copy(variant: str) -> MarketingCopyAsset:
    return MarketingCopyAsset(
        id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        platform="tiktok",
        variant_key=variant,
        language="en",
        headline=f"Variant {variant}",
        body=f"Variant {variant} body",
        cta="Shop now",
        performance_status="active",
    )


def _snapshot(
    *,
    campaign_id,
    copy_id,
    impressions: int,
    clicks: int,
    orders: int,
    spend: float,
    revenue: float,
) -> MarketingPerformanceSnapshot:
    return MarketingPerformanceSnapshot(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        campaign_id=campaign_id,
        copy_id=copy_id,
        scope_key=str(copy_id),
        platform="tiktok",
        source="manual",
        period_start=datetime(2026, 11, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 11, 7, tzinfo=timezone.utc),
        impressions=impressions,
        clicks=clicks,
        orders=orders,
        conversions=orders,
        spend=spend,
        revenue=revenue,
        currency="USD",
    )


def test_auto_pauses_clear_loser_and_marks_winner():
    variant_a = _copy("A")
    variant_b = _copy("B")
    variant_b.campaign_id = variant_a.campaign_id
    variant_b.user_id = variant_a.user_id
    snapshots = [
        _snapshot(
            campaign_id=variant_a.campaign_id,
            copy_id=variant_a.id,
            impressions=2400,
            clicks=120,
            orders=20,
            spend=100,
            revenue=520,
        ),
        _snapshot(
            campaign_id=variant_b.campaign_id,
            copy_id=variant_b.id,
            impressions=2200,
            clicks=44,
            orders=2,
            spend=100,
            revenue=30,
        ),
    ]

    results = evaluate_variant_performance([variant_a, variant_b], snapshots)
    statuses = {item["variant_key"]: item["performance_status"] for item in results}

    assert statuses == {"A": "winner", "B": "paused"}
    assert results[0]["metrics"]["roas"] == 5.2


def test_small_sample_never_auto_pauses():
    variant_a = _copy("A")
    variant_b = _copy("B")
    variant_b.campaign_id = variant_a.campaign_id
    variant_b.user_id = variant_a.user_id
    snapshots = [
        _snapshot(
            campaign_id=variant_a.campaign_id,
            copy_id=variant_a.id,
            impressions=100,
            clicks=10,
            orders=3,
            spend=10,
            revenue=80,
        ),
        _snapshot(
            campaign_id=variant_b.campaign_id,
            copy_id=variant_b.id,
            impressions=90,
            clicks=2,
            orders=0,
            spend=10,
            revenue=0,
        ),
    ]

    results = evaluate_variant_performance([variant_a, variant_b], snapshots)

    assert {
        item["performance_status"] for item in results
    } == {"insufficient_data"}


@pytest.mark.asyncio
async def test_metric_import_auto_evaluates_and_returns_actions(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="A/B 自动优化商品",
    )
    db_session.add(product)
    await db_session.flush()
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="A/B 自动优化活动",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="en",
        budget_credits=500,
        brief_json="{}",
    )
    db_session.add(campaign)
    await db_session.flush()
    batch_id = uuid.uuid4()
    variant_a = MarketingCopyAsset(
        batch_id=batch_id,
        user_id=user.id,
        campaign_id=campaign.id,
        platform="tiktok",
        variant_key="A",
        language="en",
        headline="Winner hook",
        body="Winner body",
        cta="Shop now",
    )
    variant_b = MarketingCopyAsset(
        batch_id=batch_id,
        user_id=user.id,
        campaign_id=campaign.id,
        platform="tiktok",
        variant_key="B",
        language="en",
        headline="Losing hook",
        body="Losing body",
        cta="Shop now",
    )
    db_session.add_all([variant_a, variant_b])
    await db_session.flush()

    imported = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/metrics",
        json={
            "items": [
                {
                    "platform": "tiktok",
                    "source": "tiktok_ads_api",
                    "copy_id": str(variant_a.id),
                    "period_start": "2026-11-01T00:00:00Z",
                    "period_end": "2026-11-07T23:59:59Z",
                    "impressions": 2400,
                    "clicks": 120,
                    "orders": 20,
                    "spend": 100,
                    "revenue": 520,
                },
                {
                    "platform": "tiktok",
                    "source": "tiktok_ads_api",
                    "copy_id": str(variant_b.id),
                    "period_start": "2026-11-01T00:00:00Z",
                    "period_end": "2026-11-07T23:59:59Z",
                    "impressions": 2200,
                    "clicks": 44,
                    "orders": 2,
                    "spend": 100,
                    "revenue": 30,
                },
            ]
        },
        headers=auth_headers,
    )
    assert imported.status_code == 201, imported.text
    await db_session.refresh(variant_a)
    await db_session.refresh(variant_b)
    assert variant_a.performance_status == "winner"
    assert variant_b.performance_status == "paused"

    optimization = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}/optimization",
        headers=auth_headers,
    )
    assert optimization.status_code == 200, optimization.text
    payload = optimization.json()
    assert {item["variant_key"] for item in payload["variant_analysis"]} == {
        "A",
        "B",
    }
    assert payload["variant_analysis"][0]["metrics"]["ctr"] > 0
    assert any(item["asset_type"] == "copy" for item in payload["asset_actions"])
    assert any(item["asset_type"] == "image" for item in payload["asset_actions"])

    resumed = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/copy/{variant_b.id}/resume",
        headers=auth_headers,
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["performance_status"] == "active"
