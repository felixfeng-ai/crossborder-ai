"""营销活动上下文与 Agent 绑定。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.image_generation_task import ImageGenerationTask
from app.models.marketing_video import MarketingVideoProject
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services.agent_capability_service import schedule_product_image_task
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
    assets = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}/assets",
        headers=other_headers,
    )
    assert assets.status_code == 404


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


@pytest.mark.asyncio
async def test_campaign_assets_include_bound_media(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    created = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": "素材活动",
            "objective": "conversion",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "budget_credits": 300,
        },
        headers=auth_headers,
    )
    campaign_id = uuid.UUID(created.json()["id"])
    db_session.add(ImageGenerationTask(
        user_id=user.id,
        campaign_id=campaign_id,
        prompt="节日商品主图",
        num_outputs=1,
        status="completed",
        image_urls='["https://example.com/hero.png"]',
        credits_cost=10,
        credits_charged=10,
    ))
    db_session.add(VideoGenerationTask(
        user_id=user.id,
        campaign_id=campaign_id,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        prompt="节日商品视频",
        status="succeeded",
        storage_key=f"{user.id}/campaign-video.mp4",
        credits_cost=20,
        credits_charged=20,
    ))
    db_session.add(MarketingVideoProject(
        user_id=user.id,
        campaign_id=campaign_id,
        title="节日营销成片",
        product_name="DONMIS 香薰礼盒",
        idea="圣诞送礼场景",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="succeeded",
        brief_json="{}",
        final_storage_key=f"{user.id}/campaign-project.mp4",
        credits_estimated=80,
        credits_charged=80,
    ))
    await db_session.flush()

    response = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {
        "images": 1,
        "image_tasks": 1,
        "videos": 1,
        "marketing_videos": 1,
        "total": 3,
    }
    assert {item["kind"] for item in body["items"]} == {
        "image",
        "video",
        "marketing_video",
    }
    assert body["counts"]["images"] == 1
    image_item = next(item for item in body["items"] if item["kind"] == "image")
    assert image_item["urls"] == ["https://example.com/hero.png"]
    assert image_item["thumbnail_url"] == "https://example.com/hero.png"
    video_item = next(item for item in body["items"] if item["kind"] == "video")
    assert video_item["thumbnail_url"].endswith("/thumbnail")
    project_item = next(
        item for item in body["items"] if item["kind"] == "marketing_video"
    )
    assert project_item["thumbnail_url"].endswith("/thumbnail")


@pytest.mark.asyncio
async def test_image_task_creation_persists_campaign_id(
    db_session,
    monkeypatch,
):
    from app.services import provider_config

    user = User(
        email=f"image-task-{uuid.uuid4().hex[:8]}@example.com",
        username="image-task-user",
        password_hash="x",
        plan="professional",
        credits=200,
    )
    db_session.add(user)
    await db_session.flush()
    campaign_id = uuid.uuid4()
    monkeypatch.setattr(
        provider_config,
        "get",
        lambda provider, field, default="": (
            "image-key" if provider == "aliyun" and field == "api_key" else default
        ),
    )

    task = await schedule_product_image_task(
        db_session,
        user,
        prompt="premium festive product hero image",
        num_outputs=1,
        campaign_id=str(campaign_id),
    )

    assert task.campaign_id == campaign_id
