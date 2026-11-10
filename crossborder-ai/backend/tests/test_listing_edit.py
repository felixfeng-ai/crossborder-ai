"""Listing edit, versioning and compliance recheck behavior."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.services.ai.deepseek import DeepSeekService


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": "testpass123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_standard(client: AsyncClient, db_session, headers: dict, email: str) -> None:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan = "standard"
    await db_session.flush()


async def _create_generated_listing(
    client: AsyncClient,
    headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str]:
    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "Premium wireless earbuds with long battery life."

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    product_resp = await client.post(
        "/api/v1/products/manual",
        json={
            "url": f"https://detail.1688.com/offer/edit-{uuid.uuid4().hex}.html",
            "title": "待编辑商品",
            "price": 29.9,
        },
        headers=headers,
    )
    assert product_resp.status_code == 201, product_resp.text
    product_id = product_resp.json()["product"]["id"]

    generated = await client.post(
        "/api/v1/content/generate",
        json={"product_id": product_id, "platform": "amazon", "language": "en"},
        headers=headers,
    )
    assert generated.status_code == 200, generated.text
    return product_id, generated.json()["listing_id"]


@pytest.mark.asyncio
async def test_edit_invalidates_previous_compliance(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    email = "listing-edit@example.com"
    headers = await _register(client, email)
    await _make_standard(client, db_session, headers, email)
    _, listing_id = await _create_generated_listing(client, headers, monkeypatch)

    updated = await client.put(
        f"/api/v1/listings/{listing_id}",
        json={
            "title": "Edited wireless earbuds",
            "description": "A cleaner product description.",
            "bullet_points": ["Long battery life", "Comfortable fit"],
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()
    assert data["version"] == 2
    assert data["status"] == "draft"
    assert data["compliance_status"] == "unknown"

    publish = await client.post(
        "/api/v1/shopify/push",
        json={"listing_id": listing_id, "channel_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert publish.status_code == 409, publish.text
    assert "合规报告已失效" in publish.json()["detail"]


@pytest.mark.asyncio
async def test_recheck_clean_edited_listing(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    email = "listing-recheck@example.com"
    headers = await _register(client, email)
    await _make_standard(client, db_session, headers, email)
    _, listing_id = await _create_generated_listing(client, headers, monkeypatch)

    await client.put(
        f"/api/v1/listings/{listing_id}",
        json={
            "title": "Edited wireless earbuds",
            "description": "A cleaner product description.",
            "bullet_points": ["Long battery life"],
        },
        headers=headers,
    )
    checked = await client.post(
        f"/api/v1/listings/{listing_id}/compliance",
        headers=headers,
    )
    assert checked.status_code == 200, checked.text
    data = checked.json()
    assert data["version"] == 2
    assert data["status"] == "ready"
    assert data["compliance_status"] == "pass"
    assert data["violations"] == []


@pytest.mark.asyncio
async def test_recheck_blocked_edited_listing(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register(client, "listing-recheck-block@example.com")
    _, listing_id = await _create_generated_listing(client, headers, monkeypatch)

    await client.put(
        f"/api/v1/listings/{listing_id}",
        json={
            "title": "The best wireless earbuds",
            "description": "Zero risk purchase.",
            "bullet_points": ["Perfect sound"],
        },
        headers=headers,
    )
    checked = await client.post(
        f"/api/v1/listings/{listing_id}/compliance",
        headers=headers,
    )
    assert checked.status_code == 200, checked.text
    data = checked.json()
    assert data["status"] == "blocked"
    assert data["compliance_status"] == "block"
    assert data["violations"]


@pytest.mark.asyncio
async def test_other_user_cannot_read_or_edit_listing(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    owner_headers = await _register(client, "listing-edit-owner@example.com")
    _, listing_id = await _create_generated_listing(client, owner_headers, monkeypatch)
    other_headers = await _register(client, "listing-edit-other@example.com")

    read = await client.get(f"/api/v1/listings/{listing_id}", headers=other_headers)
    assert read.status_code == 404
    update = await client.put(
        f"/api/v1/listings/{listing_id}",
        json={"title": "Hijacked"},
        headers=other_headers,
    )
    assert update.status_code == 404
    check = await client.post(
        f"/api/v1/listings/{listing_id}/compliance",
        headers=other_headers,
    )
    assert check.status_code == 404
