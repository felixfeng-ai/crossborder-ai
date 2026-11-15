"""图片编辑任务、归属校验与本地放大链路测试。"""

import io
import json
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services import provider_config
from app.services.image_task_executor import run_image_generation


def _png_bytes(size=(120, 90), color=(185, 70, 42)) -> bytes:
    image = Image.new("RGB", size, color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_config.clear_cache()
    yield
    provider_config.clear_cache()


async def _prepare_user(db_session) -> User:
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.plan = "professional"
    user.credits = 100
    await db_session.flush()
    return user


async def _upload_asset(client, headers, tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    response = await client.post(
        "/api/v1/images/assets/upload",
        files={"file": ("editable.png", _png_bytes(), "image/png")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_upscale_creates_local_task_without_external_provider(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    source_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)

    response = await client.post(
        "/api/v1/images/edit",
        json={
            "source_asset_id": source_id,
            "operation": "upscale",
            "scale": 2,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.mode == "upscale"
    assert task.provider == "local"
    assert task.credits_cost == 2
    assert source_id in task.reference_assets_json


@pytest.mark.asyncio
async def test_inpaint_requires_configured_edit_model(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    source_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    mask_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "edit-key")
    monkeypatch.setattr(settings, "REPLICATE_IMAGE_INPAINT_MODEL", "")

    response = await client.post(
        "/api/v1/images/edit",
        json={
            "source_asset_id": source_id,
            "mask_asset_id": mask_id,
            "operation": "inpaint",
            "prompt": "把包装盒背景改成暖色节日桌面",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "编辑服务" in response.json()["detail"]


@pytest.mark.asyncio
async def test_inpaint_task_records_mask_and_provider(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    source_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    mask_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "edit-key")
    monkeypatch.setattr(
        settings,
        "REPLICATE_IMAGE_INPAINT_MODEL",
        "flux-fill-test",
    )

    response = await client.post(
        "/api/v1/images/edit",
        json={
            "source_asset_id": source_id,
            "mask_asset_id": mask_id,
            "operation": "inpaint",
            "prompt": "局部替换为干净的米白色台面",
            "aspect_ratio": "4:5",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.mode == "inpaint"
    assert task.provider == "replicate"
    assert task.credits_cost == 6
    assert mask_id in json.loads(task.reference_assets_json)
    assert json.loads(task.generation_params_json)["mask_asset_id"] == mask_id


@pytest.mark.asyncio
async def test_edit_rejects_other_user_source(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    source_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    other_email = f"edit-other-{uuid.uuid4().hex[:6]}@example.com"
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "username": "edit-other",
            "password": "testpass123",
        },
    )
    other_user = (
        await db_session.execute(select(User).where(User.email == other_email))
    ).scalar_one()
    other_user.plan = "professional"
    other_user.credits = 100
    await db_session.flush()

    response = await client.post(
        "/api/v1/images/edit",
        json={
            "source_asset_id": source_id,
            "operation": "upscale",
            "scale": 2,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )

    assert response.status_code == 404
    assert "素材" in response.json()["detail"]


@pytest.mark.asyncio
async def test_local_upscale_executor_materializes_larger_asset(
    db_session,
    tmp_path,
    monkeypatch,
):
    user = User(
        email=f"upscale-{uuid.uuid4().hex[:8]}@example.com",
        username="upscale-user",
        password_hash="x",
        plan="professional",
        credits=20,
    )
    db_session.add(user)
    await db_session.flush()
    storage_key = f"{user.id}/upscale-source.png"
    source_path = tmp_path / storage_key
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(_png_bytes((120, 90)))
    source = ImageAsset(
        user_id=user.id,
        name="待放大图片",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=120,
        height=90,
        file_size=source_path.stat().st_size,
    )
    db_session.add(source)
    await db_session.flush()
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="图片放大",
        mode="upscale",
        provider="local",
        quality_tier=None,
        resolution="240x180",
        aspect_ratio="4:3",
        reference_assets_json=json.dumps([str(source.id)]),
        reference_coverage="provided",
        generation_params_json=json.dumps({"scale": 2}),
        num_outputs=1,
        credits_cost=2,
        status="processing",
        image_urls="[]",
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))

    await run_image_generation(db_session, task.id, task.prompt, 1)

    await db_session.refresh(task)
    assert task.status == "completed"
    generated = (
        await db_session.execute(
            select(ImageAsset).where(
                ImageAsset.generation_task_id == task.id
            )
        )
    ).scalar_one()
    assert generated.width == 240
    assert generated.height == 180
    assert (tmp_path / generated.storage_key).is_file()
