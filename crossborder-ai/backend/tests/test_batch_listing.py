"""Batch import and tenant-scoped product URL behavior."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.services.ai.deepseek import DeepSeekService


async def _make_standard(client: AsyncClient, db_session, headers: dict) -> None:
    me = await client.get("/api/v1/auth/me", headers=headers)
    user = (
        await db_session.execute(
            select(User).where(User.id == uuid.UUID(me.json()["id"]))
        )
    ).scalar_one()
    user.plan = "standard"
    await db_session.flush()


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
    assert me.json()["credits"] == 29


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
