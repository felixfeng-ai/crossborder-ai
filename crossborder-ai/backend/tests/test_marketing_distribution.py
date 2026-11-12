"""活动发布记录与效果数据回流。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_distribution import MarketingCampaignPublication
from app.models.user import User


async def _campaign_for_user(client, headers, db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    campaign = MarketingCampaign(
        user_id=user.id,
        title="发布效果活动",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="en",
        budget_credits=500,
        brief_json="{}",
    )
    db_session.add(campaign)
    await db_session.flush()
    return user, campaign


@pytest.mark.asyncio
async def test_amazon_publication_requires_real_listing_context(
    client,
    auth_headers,
    db_session,
):
    _, campaign = await _campaign_for_user(client, auth_headers, db_session)
    response = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/publications",
        json={"platform": "amazon"},
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text
    assert "product type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_campaign_metrics_import_and_aggregate(
    client,
    auth_headers,
    db_session,
):
    _, campaign = await _campaign_for_user(client, auth_headers, db_session)
    response = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/metrics",
        json={
            "items": [
                {
                    "platform": "tiktok",
                    "source": "manual",
                    "period_start": "2026-11-01T00:00:00Z",
                    "period_end": "2026-11-07T23:59:59Z",
                    "impressions": 10000,
                    "clicks": 500,
                    "orders": 40,
                    "conversions": 40,
                    "spend": 200,
                    "revenue": 1200,
                    "currency": "USD",
                    "metadata": {"campaign_name": "holiday"},
                }
            ]
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["total"] == 1

    performance = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}/performance",
        headers=auth_headers,
    )
    assert performance.status_code == 200, performance.text
    totals = performance.json()["totals"]
    assert totals["impressions"] == 10000
    assert totals["clicks"] == 500
    assert totals["ctr"] == 5.0
    assert totals["roas"] == 6.0
    optimization = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}/optimization",
        headers=auth_headers,
    )
    assert optimization.status_code == 200, optimization.text
    codes = {
        item["code"] for item in optimization.json()["recommendations"]
    }
    assert "scale_winner" in codes
    assert "connect_variant_metrics" in codes

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"distribution-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "distribution-other",
            "password": "testpass123",
        },
    )
    foreign = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}/performance",
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )
    assert foreign.status_code == 404
