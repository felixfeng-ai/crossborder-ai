"""营销多平台图片套图契约。"""

import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.models.image_generation_task import ImageGenerationTask
from app.models.marketing_image_suite import MarketingImageSuite
from app.models.user import User
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.services import provider_config
from app.services.workspaces import ensure_personal_workspace


def _png_bytes(color=(155, 92, 42)) -> bytes:
    image = Image.new("RGB", (240, 240), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_config.clear_cache()
    yield
    provider_config.clear_cache()


async def _prepare_user(db_session, *, credits: int = 100) -> User:
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.plan = "professional"
    personal = await ensure_personal_workspace(db_session, user)
    workspace_wallet = await db_session.get(
        WorkspaceCreditWallet,
        personal.id,
    )
    assert workspace_wallet is not None
    workspace_wallet.plan_credits = credits
    workspace_wallet.purchased_credits = 0
    user.credits = credits
    await db_session.flush()
    return user


async def _upload_asset(client, headers, tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    response = await client.post(
        "/api/v1/images/assets/upload",
        files={"file": ("suite-reference.png", _png_bytes(), "image/png")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_campaign(client, headers) -> str:
    response = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": "圣诞香薰片套图",
            "objective": "conversion",
            "platform": "multi",
            "market": "US",
            "language": "en",
            "budget_credits": 300,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_marketing_suite_creates_one_task_per_platform(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    campaign_id = await _create_campaign(client, auth_headers)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "reference-key")
    monkeypatch.setattr(
        settings,
        "REPLICATE_IMAGE_REFERENCE_MODEL",
        "seedream-reference",
    )

    response = await client.post(
        "/api/v1/images/marketing-suites",
        json={
            "campaign_id": campaign_id,
            "title": "圣诞转化套图",
            "direction": "conversion",
            "theme": "christmas",
            "platforms": ["amazon-main", "tiktok-main", "shopify-product"],
            "reference_asset_ids": [reference_id],
            "quality_tier": "fast",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["total_credits"] == 24
    assert len(body["items"]) == 3
    assert {item["platform"] for item in body["items"]} == {
        "amazon-main",
        "tiktok-main",
        "shopify-product",
    }

    suite = await db_session.get(MarketingImageSuite, uuid.UUID(body["suite_id"]))
    assert suite.campaign_id == uuid.UUID(campaign_id)
    tasks = (
        await db_session.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.campaign_id == uuid.UUID(campaign_id),
                ImageGenerationTask.mode == "product_scene",
            )
        )
    ).scalars().all()
    assert len(tasks) == 3
    assert all(task.credits_cost == 8 for task in tasks)
    assert all(reference_id in task.reference_assets_json for task in tasks)


@pytest.mark.asyncio
async def test_marketing_suite_idempotency_returns_existing_suite(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    campaign_id = await _create_campaign(client, auth_headers)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "reference-key")
    payload = {
        "campaign_id": campaign_id,
        "title": "节日套图",
        "direction": "conversion",
        "theme": "holiday",
        "platforms": ["amazon-main", "shopify-product"],
        "reference_asset_ids": [reference_id],
        "quality_tier": "fast",
        "idempotency_key": str(uuid.uuid4()),
    }

    first = await client.post(
        "/api/v1/images/marketing-suites",
        json=payload,
        headers=auth_headers,
    )
    second = await client.post(
        "/api/v1/images/marketing-suites",
        json=payload,
        headers=auth_headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code in {200, 201}, second.text
    assert first.json()["suite_id"] == second.json()["suite_id"]
    count = (
        await db_session.execute(
            select(func.count(MarketingImageSuite.id)).where(
                MarketingImageSuite.idempotency_key
                == payload["idempotency_key"]
            )
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_marketing_suite_rejects_foreign_reference_and_insufficient_credits(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session, credits=5)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    campaign_id = await _create_campaign(client, auth_headers)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "reference-key")
    payload = {
        "campaign_id": campaign_id,
        "title": "节日套图",
        "direction": "conversion",
        "theme": "holiday",
        "platforms": ["amazon-main", "shopify-product"],
        "reference_asset_ids": [reference_id],
        "quality_tier": "fast",
        "idempotency_key": str(uuid.uuid4()),
    }

    insufficient = await client.post(
        "/api/v1/images/marketing-suites",
        json=payload,
        headers=auth_headers,
    )
    assert insufficient.status_code == 402
    assert "积分" in insufficient.json()["detail"]

    other_email = f"suite-other-{uuid.uuid4().hex[:6]}@example.com"
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "username": "suite-other",
            "password": "testpass123",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other.json()['access_token']}",
    }
    other_user = (
        await db_session.execute(
            select(User).where(User.email == other_email)
        )
    ).scalar_one()
    other_user.plan = "professional"
    other_user.credits = 100
    await db_session.flush()
    foreign = await client.post(
        "/api/v1/images/marketing-suites",
        json={
            **payload,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=other_headers,
    )
    assert foreign.status_code == 404
    assert "素材" in foreign.json()["detail"] or "活动" in foreign.json()["detail"]


@pytest.mark.asyncio
async def test_campaign_assets_expose_suite_and_platform_metadata(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    campaign_id = await _create_campaign(client, auth_headers)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "reference-key")
    created = await client.post(
        "/api/v1/images/marketing-suites",
        json={
            "campaign_id": campaign_id,
            "title": "双平台套图",
            "direction": "lifestyle",
            "theme": "winter",
            "platforms": ["amazon-main", "tiktok-main"],
            "reference_asset_ids": [reference_id],
            "quality_tier": "fast",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    response = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    image_items = [
        item for item in response.json()["items"] if item["kind"] == "image"
    ]
    assert len(image_items) == 2
    assert {item["platform"] for item in image_items} == {
        "amazon-main",
        "tiktok-main",
    }
    assert {item["suite_id"] for item in image_items} == {created.json()["suite_id"]}
