"""Batch import and tenant-scoped product URL behavior."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.services.ai.deepseek import DeepSeekService
from app.services.plan_service import activate_paid_plan


async def _make_standard(client: AsyncClient, db_session, headers: dict) -> None:
    me = await client.get("/api/v1/auth/me", headers=headers)
    user = (
        await db_session.execute(
            select(User).where(User.id == uuid.UUID(me.json()["id"]))
        )
    ).scalar_one()
    await activate_paid_plan(
        db_session,
        user,
        "standard",
        source="test_activation",
    )


async def _upload_one(client: AsyncClient, headers: dict, suffix: str) -> None:
    csv_text = (
        "title,url,price,description\n"
        f"批量商品{suffix},https://detail.1688.com/offer/batch-{suffix}.html,29.90,批量描述\n"
    )
    response = await client.post(
        "/api/v1/batch/upload",
        files={"file": (f"batch-{suffix}.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _pending_job_id(client: AsyncClient, headers: dict) -> str:
    response = await client.get("/api/v1/batch/jobs", headers=headers)
    assert response.status_code == 200, response.text
    job = next(item for item in response.json()["items"] if item["status"] == "pending")
    return job["id"]


@pytest.mark.asyncio
async def test_batch_process_creates_user_owned_product(
    client: AsyncClient,
    auth_headers: dict,
):
    await _upload_one(client, auth_headers, "owned")
    job_id = await _pending_job_id(client, auth_headers)

    response = await client.post(
        f"/api/v1/batch/process/{job_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    products = await client.get("/api/v1/products", headers=auth_headers)
    assert products.status_code == 200
    assert products.json()["total"] == 1
    assert products.json()["items"][0]["title"] == "批量商品owned"


@pytest.mark.asyncio
async def test_own_product_csv_without_url_imports_rich_fields(
    client: AsyncClient,
    auth_headers: dict,
):
    csv_text = (
        "title,cost_price,currency,stock_quantity,description,main_image_url,"
        "brand_name,moq,lead_time_days,sku\n"
        "自有香薰礼盒,38.50,CNY,80,自有货源商品描述,"
        "https://cdn.example.com/gift.jpg,VEYA,20,10,OWN-GIFT-01\n"
    )
    uploaded = await client.post(
        "/api/v1/batch/upload",
        files={"file": ("own-products.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    job_id = await _pending_job_id(client, auth_headers)

    processed = await client.post(
        f"/api/v1/batch/process/{job_id}",
        headers=auth_headers,
    )
    assert processed.status_code == 200, processed.text

    products = await client.get("/api/v1/products", headers=auth_headers)
    product = products.json()["items"][0]
    assert product["title"] == "自有香薰礼盒"
    assert product["origin_type"] == "own"
    assert product["price"] == 38.5
    assert product["brand_name"] == "VEYA"
    assert product["moq"] == 20
    assert product["main_image_url"] == "https://cdn.example.com/gift.jpg"

    variants = await client.get(
        f"/api/v1/products/{product['id']}/variants",
        headers=auth_headers,
    )
    assert variants.status_code == 200
    assert variants.json()["items"][0]["sku"] == "OWN-GIFT-01"
    assert variants.json()["items"][0]["stock_quantity"] == 80


@pytest.mark.asyncio
async def test_batch_ai_persists_listing_and_charges_once(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    await _make_standard(client, db_session, auth_headers)

    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "Premium wireless earbuds with long battery life."

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    await _upload_one(client, auth_headers, "ai")

    response = await client.post("/api/v1/batch/process-ai", headers=auth_headers)
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "success"
    assert result["product_id"]
    assert result["listing_id"]

    history = await client.get(
        f"/api/v1/products/{result['product_id']}/listings",
        headers=auth_headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == result["listing_id"]

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.json()["credits"] == 799


@pytest.mark.asyncio
async def test_same_product_url_allowed_for_different_users(
    client: AsyncClient,
    auth_headers: dict,
):
    payload = {
        "url": "https://detail.1688.com/offer/shared-url.html",
        "title": "共享链接商品",
        "price": 19.9,
    }
    first = await client.post(
        "/api/v1/products/manual",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "tenant-url-second@example.com",
            "username": "tenant-url-second",
            "password": "testpass123",
        },
    )
    assert second.status_code == 201, second.text
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    duplicate = await client.post(
        "/api/v1/products/manual",
        json=payload,
        headers=second_headers,
    )
    assert duplicate.status_code == 201, duplicate.text
