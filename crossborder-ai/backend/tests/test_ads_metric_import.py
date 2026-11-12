"""Amazon Ads、TikTok Ads、Meta Ads CSV 适配器测试。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import MarketingPerformanceSnapshot
from app.models.product import Product
from app.models.user import User
from app.services.ads_metric_import import (
    AdsMetricImportError,
    parse_ad_metrics_csv,
)


def test_parse_amazon_ads_standard_report():
    csv_text = """date,impressions,clicks,cost,purchases,sales
2026-11-01,1200,36,18.5,4,120
2026-11-02,800,20,9.5,2,60
"""

    result = parse_ad_metrics_csv("amazon_ads", csv_text)

    assert result.platform == "amazon"
    assert result.source == "amazon_ads_csv"
    assert result.impressions == 2000
    assert result.clicks == 56
    assert result.orders == 6
    assert result.conversions == 6
    assert result.spend == 28.0
    assert result.revenue == 180.0


def test_parse_tiktok_ads_localized_headers_and_currency():
    csv_text = """Impressions,Clicks,Cost,Complete Payment,Complete Payment Value
"1,500","45","$20.50","3","$99.00"
"""

    result = parse_ad_metrics_csv("tiktok_ads", csv_text)

    assert result.platform == "tiktok"
    assert result.impressions == 1500
    assert result.clicks == 45
    assert result.spend == 20.5
    assert result.orders == 3
    assert result.revenue == 99.0


def test_parse_meta_ads_standard_report():
    csv_text = """Amount Spent (USD),Impressions,Link Clicks,Purchases,Purchase Conversion Value
35.75,2400,96,8,320
"""

    result = parse_ad_metrics_csv("meta_ads", csv_text)

    assert result.platform == "meta"
    assert result.impressions == 2400
    assert result.clicks == 96
    assert result.spend == 35.75
    assert result.orders == 8
    assert result.revenue == 320


def test_import_rejects_invalid_row_with_line_number():
    csv_text = """impressions,clicks,spend,purchases,revenue
1000,20,10,2,50
not-a-number,5,1,0,0
"""

    with pytest.raises(AdsMetricImportError, match="第 3 行"):
        parse_ad_metrics_csv("tiktok_ads", csv_text)


@pytest.mark.asyncio
async def test_csv_import_binds_activity_and_copy(
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
        title="广告导入测试商品",
    )
    db_session.add(product)
    await db_session.flush()
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="广告导入测试活动",
        objective="conversion",
        platform="meta",
        market="US",
        language="en",
        budget_credits=300,
        brief_json="{}",
    )
    db_session.add(campaign)
    await db_session.flush()
    copy_asset = MarketingCopyAsset(
        batch_id=uuid.uuid4(),
        user_id=user.id,
        campaign_id=campaign.id,
        platform="meta",
        variant_key="A",
        language="en",
        headline="Meta A",
        body="Meta A body",
        cta="Shop now",
    )
    db_session.add(copy_asset)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/metrics/import",
        json={
            "provider": "meta_ads",
            "period_start": "2026-11-01T00:00:00Z",
            "period_end": "2026-11-07T23:59:59Z",
            "copy_id": str(copy_asset.id),
            "csv_text": (
                "Amount Spent (USD),Impressions,Link Clicks,"
                "Purchases,Purchase Conversion Value\n"
                "35.75,2400,96,8,320\n"
            ),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["item"]["copy_id"] == str(copy_asset.id)
    assert response.json()["item"]["platform"] == "meta"
    snapshot = (
        await db_session.execute(
            select(MarketingPerformanceSnapshot).where(
                MarketingPerformanceSnapshot.campaign_id == campaign.id
            )
        )
    ).scalar_one()
    assert snapshot.copy_id == copy_asset.id
    assert snapshot.scope_key == str(copy_asset.id)
