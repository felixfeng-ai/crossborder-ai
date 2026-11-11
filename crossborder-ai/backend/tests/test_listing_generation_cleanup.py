"""Listing 生成页面收敛后的行为契约。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.image_generation_task import ImageGenerationTask
from app.models.product import Product
from app.models.user import User
from app.services.ai.deepseek import DeepSeekService


async def _register(client: AsyncClient) -> tuple[dict, str]:
    email = f"listing-cleanup-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": "listing-cleanup",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _create_product(
    db_session,
    email: str,
    *,
    description: str = "20ml body oil with fast absorption",
    main_image_url: str = "https://cdn.example.com/product.webp",
) -> Product:
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Terra Body Oil",
        description=description,
        price=29.9,
        sales_count=1280,
        shop_name="Terra Official",
        main_image_url=main_image_url,
    )
    db_session.add(product)
    await db_session.flush()
    return product


@pytest.mark.asyncio
async def test_legacy_expert_and_image_options_are_ignored(
    client: AsyncClient,
    db_session,
    monkeypatch,
):
    headers, email = await _register(client)
    product = await _create_product(db_session, email)
    agent_called = False
    image_scheduled = False

    async def fake_agent_run(*args, **kwargs):
        nonlocal agent_called
        agent_called = True
        return {
            "title": "Agent title",
            "description": "Agent description",
            "bullet_points": ["Agent bullet"],
            "seo_title": "Agent SEO",
            "seo_description": "Agent SEO description",
        }

    async def fake_schedule(*args, **kwargs):
        nonlocal image_scheduled
        image_scheduled = True
        return str(uuid.uuid4())

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "Terra Body Oil for Daily Use"

    async def fake_description(self, **kwargs):
        return "<p>Detailed product description</p>"

    async def fake_bullets(self, **kwargs):
        return ["Fast absorption", "Lightweight finish"]

    async def fake_seo(self, **kwargs):
        return {
            "seo_title": "Terra Body Oil",
            "seo_description": "Fast-absorbing daily body oil.",
        }

    monkeypatch.setattr("app.services.ai.agent.ListingAgent.run", fake_agent_run)
    monkeypatch.setattr("app.routers.images.schedule_image_task", fake_schedule)
    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    monkeypatch.setattr(
        DeepSeekService,
        "generate_product_description",
        fake_description,
    )
    monkeypatch.setattr(DeepSeekService, "generate_bullet_points", fake_bullets)
    monkeypatch.setattr(DeepSeekService, "optimize_seo", fake_seo)

    response = await client.post(
        "/api/v1/content/generate",
        json={
            "product_id": str(product.id),
            "platform": "amazon",
            "language": "en",
            "tone": "professional",
            "expert_mode": True,
            "generate_image": True,
            "image_prompt": "Generate a fake packshot",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert agent_called is False
    assert image_scheduled is False
    assert response.json()["image_task_id"] == ""
    image_task_count = await db_session.scalar(
        select(func.count()).select_from(ImageGenerationTask)
    )
    assert image_task_count == 0


@pytest.mark.asyncio
async def test_listing_prompts_use_richer_product_facts(
    client: AsyncClient,
    db_session,
    monkeypatch,
):
    headers, email = await _register(client)
    product = await _create_product(
        db_session,
        email,
        description="Cold-pressed body oil for sensitive skin",
    )
    captured: dict[str, str] = {}

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "Terra Cold Pressed Body Oil"

    async def fake_description(self, **kwargs):
        captured["description_features"] = kwargs.get("product_features") or ""
        return "<p>Detailed body oil description</p>"

    async def fake_bullets(self, **kwargs):
        captured["bullet_features"] = kwargs.get("features") or ""
        return ["Sensitive skin friendly", "Fast absorption"]

    async def fake_seo(self, **kwargs):
        return {"seo_title": "Terra Body Oil", "seo_description": "Body oil"}

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    monkeypatch.setattr(
        DeepSeekService,
        "generate_product_description",
        fake_description,
    )
    monkeypatch.setattr(DeepSeekService, "generate_bullet_points", fake_bullets)
    monkeypatch.setattr(DeepSeekService, "optimize_seo", fake_seo)

    response = await client.post(
        "/api/v1/content/generate",
        json={
            "product_id": str(product.id),
            "platform": "amazon",
            "language": "en",
            "tone": "professional",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "Cold-pressed body oil" in captured["description_features"]
    assert "Cold-pressed body oil" in captured["bullet_features"]
    assert "29.9" in captured["bullet_features"]
    assert "1280" in captured["bullet_features"]
    assert "Terra Official" in captured["bullet_features"]


@pytest.mark.asyncio
async def test_a_plus_generation_remains_available(
    client: AsyncClient,
    db_session,
    monkeypatch,
):
    headers, email = await _register(client)
    product = await _create_product(db_session, email)

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "<h2>Terra Body Oil</h2><p>Fast absorption for daily use.</p>"

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    response = await client.post(
        "/api/v1/content/a-plus",
        json={
            "product_id": str(product.id),
            "platform": "amazon",
            "language": "en",
            "tone": "professional",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "Terra Body Oil" in response.json()["html"]
    assert response.json()["blocked"] is False
