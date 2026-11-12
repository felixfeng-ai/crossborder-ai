"""生成图片自动入库与视频首帧复用。"""

import io
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services.ai.aliyun_image import AliyunImageService
from app.services.image_task_executor import run_image_generation
import app.services.image_task_executor as image_executor
import app.services.generated_image_assets as generated_assets


def _png_bytes(size=(160, 120)) -> bytes:
    image = Image.new("RGB", size, (54, 110, 180))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _FakeImageResponse:
    content = _png_bytes()
    headers = {"content-type": "image/png"}

    def raise_for_status(self) -> None:
        return None


async def _fake_download(self, url, *args, **kwargs):
    return _FakeImageResponse()


async def _create_user(db_session, *, credits: int = 20) -> User:
    user = User(
        email=f"generated-assets-{uuid.uuid4().hex[:8]}@example.com",
        username="generated-assets",
        password_hash="x",
        credits=credits,
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_generated_image_outputs_are_materialized_idempotently(
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _create_user(db_session)
    campaign_id = uuid.uuid4()
    task = ImageGenerationTask(
        user_id=user.id,
        campaign_id=campaign_id,
        prompt="premium festive product hero",
        num_outputs=2,
        status="processing",
        image_urls="[]",
        credits_cost=2,
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_executor.provider_config,
        "get",
        lambda group, key, default="": (
            "test-key" if group == "aliyun" and key == "api_key" else default
        ),
    )

    async def fake_generate_image(self, prompt, num_outputs=1, size="1024*1024"):
        return [
            "https://cdn.example.com/generated-a.png",
            "https://cdn.example.com/generated-b.png",
        ]

    monkeypatch.setattr(AliyunImageService, "generate_image", fake_generate_image)
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_download)

    await run_image_generation(db_session, task.id, task.prompt, task.num_outputs)
    await run_image_generation(db_session, task.id, task.prompt, task.num_outputs)

    await db_session.refresh(task)
    assets = (
        await db_session.execute(
            select(ImageAsset)
            .where(ImageAsset.generation_task_id == task.id)
            .order_by(ImageAsset.variant_index)
        )
    ).scalars().all()

    assert task.status == "completed"
    assert len(assets) == 2
    assert [asset.variant_index for asset in assets] == [0, 1]
    assert {asset.kind for asset in assets} == {"generated"}
    assert all((tmp_path / asset.storage_key).is_file() for asset in assets)
    assert all(asset.user_id == user.id for asset in assets)


@pytest.mark.asyncio
async def test_one_materialization_failure_does_not_fail_generation(
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _create_user(db_session)
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="partial generated product image",
        num_outputs=2,
        status="processing",
        image_urls="[]",
        credits_cost=2,
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_executor.provider_config,
        "get",
        lambda group, key, default="": (
            "test-key" if group == "aliyun" and key == "api_key" else default
        ),
    )

    async def fake_generate_image(self, prompt, num_outputs=1, size="1024*1024"):
        return [
            "https://cdn.example.com/broken.png",
            "https://cdn.example.com/valid.png",
        ]

    async def partial_download(url: str) -> bytes:
        if "broken" in url:
            raise ValueError("simulated download failure")
        return _png_bytes()

    monkeypatch.setattr(AliyunImageService, "generate_image", fake_generate_image)
    monkeypatch.setattr(generated_assets, "download_generated_image", partial_download)

    await run_image_generation(db_session, task.id, task.prompt, task.num_outputs)

    await db_session.refresh(task)
    assets = (
        await db_session.execute(
            select(ImageAsset).where(ImageAsset.generation_task_id == task.id)
        )
    ).scalars().all()
    assert task.status == "completed"
    assert len(assets) == 1
    assert assets[0].variant_index == 1
    assert task.credits_charged == 2


@pytest.mark.asyncio
async def test_campaign_assets_expose_materialized_image_asset_id(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    campaign = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": "图片转视频活动",
            "objective": "conversion",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "budget_credits": 200,
        },
        headers=auth_headers,
    )
    campaign_id = uuid.UUID(campaign.json()["id"])
    task = ImageGenerationTask(
        user_id=user.id,
        campaign_id=campaign_id,
        prompt="festive hero image",
        num_outputs=1,
        status="completed",
        image_urls='["https://cdn.example.com/generated.png"]',
        credits_cost=1,
        credits_charged=1,
    )
    db_session.add(task)
    await db_session.flush()
    generated_asset = ImageAsset(
        user_id=user.id,
        name="AI 生成 · festive hero image",
        kind="generated",
        storage_key=f"{user.id}/generated-{task.id}-0.webp",
        content_type="image/webp",
        width=160,
        height=120,
        file_size=1024,
        generation_task_id=task.id,
        variant_index=0,
    )
    db_session.add(generated_asset)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/marketing-campaigns/{campaign_id}/assets",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    image_item = next(
        item for item in response.json()["items"] if item["kind"] == "image"
    )
    assert image_item["image_asset_id"] == str(generated_asset.id)


@pytest.mark.asyncio
async def test_materialize_history_is_owner_scoped_and_idempotent(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="legacy generated image",
        num_outputs=1,
        status="completed",
        image_urls='["https://cdn.example.com/legacy.png"]',
        credits_cost=1,
        credits_charged=1,
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_download)

    first = await client.post(
        f"/api/v1/images/history/{task.id}/materialize",
        headers=auth_headers,
    )
    second = await client.post(
        f"/api/v1/images/history/{task.id}/materialize",
        headers=auth_headers,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert [item["id"] for item in first.json()["items"]] == [
        item["id"] for item in second.json()["items"]
    ]

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"generated-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "generated-other",
            "password": "testpass123",
        },
    )
    foreign = await client.post(
        f"/api/v1/images/history/{task.id}/materialize",
        headers={
            "Authorization": f"Bearer {other.json()['access_token']}",
        },
    )
    assert foreign.status_code == 404
