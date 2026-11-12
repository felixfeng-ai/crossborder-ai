"""营销图片批量生成、变体展示与删除。"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
import app.routers.images as images_router


async def _create_campaign(client, headers, title: str = "批量图片活动") -> str:
    response = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": title,
            "objective": "conversion",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "budget_credits": 300,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_generate_image_accepts_campaign_and_batch_size(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    user.credits = 100
    await db_session.flush()
    campaign_id = await _create_campaign(client, auth_headers)
    monkeypatch.setattr(
        images_router.provider_config,
        "get",
        lambda provider, key, default="": (
            "image-key" if provider == "aliyun" and key == "api_key" else default
        ),
    )

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "prompt": "四种不同构图的节日商品主图",
            "num_outputs": 4,
            "campaign_id": campaign_id,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = (
        await db_session.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.id == uuid.UUID(response.json()["task_id"])
            )
        )
    ).scalar_one()
    assert task.campaign_id == uuid.UUID(campaign_id)
    assert task.num_outputs == 4


@pytest.mark.asyncio
async def test_generate_image_rejects_foreign_campaign(
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
    user.credits = 100
    await db_session.flush()
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"batch-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "batch-other",
            "password": "testpass123",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other.json()['access_token']}",
    }
    foreign_campaign_id = await _create_campaign(client, other_headers)

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "prompt": "批量商品图",
            "num_outputs": 2,
            "campaign_id": foreign_campaign_id,
        },
        headers=auth_headers,
    )

    assert response.status_code in {403, 404}


@pytest.mark.asyncio
async def test_campaign_assets_return_each_generated_variant(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    campaign_id = await _create_campaign(client, auth_headers)
    task = ImageGenerationTask(
        user_id=user.id,
        campaign_id=uuid.UUID(campaign_id),
        prompt="批量节日场景图",
        num_outputs=2,
        status="completed",
        image_urls='["https://cdn.example.com/a.png", "https://cdn.example.com/b.png"]',
        credits_cost=6,
        credits_charged=6,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add_all([
        ImageAsset(
            user_id=user.id,
            name="变体 01 · 暖光",
            kind="generated",
            storage_key=f"{user.id}/variant-a.webp",
            content_type="image/webp",
            width=1024,
            height=1024,
            file_size=1000,
            generation_task_id=task.id,
            variant_index=0,
        ),
        ImageAsset(
            user_id=user.id,
            name="变体 02 · 冷光",
            kind="generated",
            storage_key=f"{user.id}/variant-b.webp",
            content_type="image/webp",
            width=1024,
            height=1024,
            file_size=1000,
            generation_task_id=task.id,
            variant_index=1,
        ),
    ])
    await db_session.flush()

    response = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["images"] == 2
    assert body["counts"]["image_tasks"] == 1
    image_item = next(item for item in body["items"] if item["kind"] == "image")
    assert [variant["name"] for variant in image_item["variants"]] == [
        "变体 01 · 暖光",
        "变体 02 · 冷光",
    ]
    assert [variant["variant_index"] for variant in image_item["variants"]] == [0, 1]


@pytest.mark.asyncio
async def test_rename_and_delete_variant_are_owner_scoped(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    campaign_id = await _create_campaign(client, auth_headers)
    task = ImageGenerationTask(
        user_id=user.id,
        campaign_id=uuid.UUID(campaign_id),
        prompt="可编辑变体",
        num_outputs=1,
        status="completed",
        image_urls='["https://cdn.example.com/edit.png"]',
        credits_cost=3,
        credits_charged=3,
    )
    db_session.add(task)
    await db_session.flush()
    path = tmp_path / f"{user.id}/editable.webp"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"webp")
    asset = ImageAsset(
        user_id=user.id,
        name="原始名称",
        kind="generated",
        storage_key=f"{user.id}/editable.webp",
        content_type="image/webp",
        width=1024,
        height=1024,
        file_size=4,
        generation_task_id=task.id,
        variant_index=0,
    )
    db_session.add(asset)
    await db_session.flush()

    renamed = await client.patch(
        f"/api/v1/images/assets/{asset.id}",
        json={"name": "节日主图 A"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "节日主图 A"

    deleted = await client.delete(
        f"/api/v1/images/assets/{asset.id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204
    await db_session.refresh(task)
    assert task.image_urls == "[]"
    activity = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}/assets",
        headers=auth_headers,
    )
    assert activity.json()["counts"]["images"] == 0

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"variant-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "variant-other",
            "password": "testpass123",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other.json()['access_token']}",
    }
    foreign_asset = ImageAsset(
        user_id=user.id,
        name="不可编辑",
        kind="upload",
        storage_key=f"{user.id}/private.webp",
        content_type="image/webp",
        width=100,
        height=100,
        file_size=4,
    )
    db_session.add(foreign_asset)
    await db_session.flush()
    foreign_rename = await client.patch(
        f"/api/v1/images/assets/{foreign_asset.id}",
        json={"name": "越权改名"},
        headers=other_headers,
    )
    foreign_delete = await client.delete(
        f"/api/v1/images/assets/{foreign_asset.id}",
        headers=other_headers,
    )
    assert foreign_rename.status_code == 404
    assert foreign_delete.status_code == 404
