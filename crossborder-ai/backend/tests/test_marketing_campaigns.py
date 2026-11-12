"""营销活动上下文与 Agent 绑定。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.user import User
from app.services.agent_task_executor import build_campaign_context


@pytest.mark.asyncio
async def test_create_and_list_marketing_campaign(client, auth_headers):
    response = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": "圣诞礼盒推广",
            "objective": "conversion",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "budget_credits": 800,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "圣诞礼盒推广"
    assert body["status"] == "planning"
    assert body["budget_credits"] == 800

    listed = await client.get(
        "/api/v1/marketing-campaigns",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [body["id"]]


@pytest.mark.asyncio
async def test_campaign_is_isolated_between_users(
    client,
    auth_headers,
):
    created = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": "私有活动",
            "objective": "traffic",
            "platform": "meta",
            "market": "UK",
            "language": "en",
            "budget_credits": 100,
        },
        headers=auth_headers,
    )
    campaign_id = created.json()["id"]

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"campaign-other-{uuid.uuid4().hex[:6]}@example.com",
            "username": "campaign-other",
            "password": "testpass123",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other.json()['access_token']}",
    }
    response = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}",
        headers=other_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_rejects_unknown_campaign(
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
    await db_session.flush()
    response = await client.post(
        "/api/v1/agent/run",
        json={
            "instruction": "为活动生成营销图片",
            "workspace": "marketing",
            "campaign_id": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert "活动" in response.text


def test_campaign_context_contains_product_and_budget():
    from types import SimpleNamespace

    campaign = SimpleNamespace(
        title="圣诞礼盒推广",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="en",
        budget_credits=800,
        spent_credits=120,
        brief_json='{"offer":"满199减30"}',
    )
    product = SimpleNamespace(
        title="DONMIS 香薰礼盒",
        url="https://detail.1688.com/offer/1.html",
        price=59.9,
        brand_name="DONMIS",
        description="节日香薰礼盒",
    )

    context = build_campaign_context(campaign, product)

    assert "圣诞礼盒推广" in context
    assert "DONMIS 香薰礼盒" in context
    assert "800" in context
    assert "满199减30" in context
