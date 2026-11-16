"""图片生成三模式、参考图、幂等和积分契约。"""

import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.routers import images as images_router
from app.services import provider_config


def _image_bytes() -> bytes:
    image = Image.new("RGB", (320, 320), (210, 90, 40))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_config.clear_cache()
    yield
    provider_config.clear_cache()


async def _prepare_user(db_session, *, plan: str = "professional") -> User:
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.plan = plan
    user.credits = 100
    await db_session.flush()
    return user


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "email": email,
    }


async def _upload_asset(
    client: AsyncClient,
    headers: dict,
    tmp_path,
    monkeypatch,
) -> str:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    response = await client.post(
        "/api/v1/images/assets/upload",
        files={"file": ("reference.png", _image_bytes(), "image/png")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _noop_execute(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_image_capabilities_expose_modes_and_quality_tiers(
    client: AsyncClient,
    auth_headers: dict,
):
    response = await client.get("/api/v1/images/capabilities", headers=auth_headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert {"product_scene", "free_creation"} <= {
        item["id"] for item in data["modes"]
    }
    assert {"fast", "standard", "hd"} <= {
        item["id"] for item in data["quality_tiers"]
    }


@pytest.mark.asyncio
async def test_free_creation_does_not_inject_brand_persona(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    await _prepare_user(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)
    prompt = "黑白电影感抽象海报，只有几何形体"

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "free_creation",
            "prompt": prompt,
            "quality_tier": "fast",
            "use_brand_persona": False,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.mode == "free_creation"
    assert task.prompt == prompt
    assert task.use_brand_persona is False
    assert task.credits_cost == 3


@pytest.mark.asyncio
async def test_realistic_free_creation_gets_photoreal_negative_prompt(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    await _prepare_user(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "free_creation",
            "prompt": "女团跳舞，要求人物真实，真人感，自然皮肤",
            "quality_tier": "standard",
            "negative_prompt": "",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert "蜡像感" in task.negative_prompt
    assert "塑料皮肤" in task.negative_prompt


@pytest.mark.asyncio
async def test_product_scene_requires_owned_reference_and_uses_scene_credit(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "test-key")
    monkeypatch.setattr(
        settings,
        "REPLICATE_IMAGE_REFERENCE_MODEL",
        "reference-image-model",
    )
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "product_scene",
            "prompt": "保持商品完全一致，放入圣诞客厅场景",
            "reference_asset_ids": [reference_id],
            "quality_tier": "hd",
            "use_brand_persona": True,
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.mode == "product_scene"
    assert reference_id in task.reference_assets_json
    assert task.reference_coverage == "provided"
    assert task.credits_cost == 12


@pytest.mark.asyncio
async def test_product_scene_accepts_seedream_without_replicate(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "SEEDREAM_API_KEY", "ark-test-key")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")
    monkeypatch.setattr(settings, "REPLICATE_IMAGE_REFERENCE_MODEL", "")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "product_scene",
            "prompt": "保持商品一致，生成冬季客厅场景",
            "reference_asset_ids": [reference_id],
            "quality_tier": "standard",
            "provider": "seedream",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.provider == "seedream"
    assert task.mode == "product_scene"


@pytest.mark.asyncio
async def test_product_scene_text_only_uses_free_creation_credit(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    """无参考图时按文字生成，不强制 Seedream/Replicate 参考图能力。"""
    await _prepare_user(db_session)
    monkeypatch.setattr(settings, "SEEDREAM_API_KEY", "ark-test-key")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")
    monkeypatch.setattr(settings, "REPLICATE_IMAGE_REFERENCE_MODEL", "")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "product_scene",
            "prompt": "外贸圣诞装饰品，木质桌面，暖光商业摄影",
            "reference_asset_ids": [],
            "quality_tier": "standard",
            "provider": "seedream",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.mode == "product_scene"
    assert task.reference_assets_json == "[]"
    assert task.reference_coverage == "none"
    assert task.credits_cost == 5


@pytest.mark.asyncio
async def test_free_creation_accepts_seedream_without_replicate(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    await _prepare_user(db_session)
    monkeypatch.setattr(settings, "SEEDREAM_API_KEY", "ark-test-key")
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "free_creation",
            "prompt": "黑白电影感女团海报，真人摄影",
            "quality_tier": "standard",
            "provider": "seedream",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.provider == "seedream"
    assert task.mode == "free_creation"


@pytest.mark.asyncio
async def test_product_scene_rejects_other_users_reference(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    other_headers = await _register(
        client,
        f"image-other-{uuid.uuid4().hex[:6]}@example.com",
    )
    # 用注册时返回的邮箱精确定位数据库用户，避免误用 token 文本或时间排序。
    other = (
        await db_session.execute(
            select(User).where(User.email == other_headers["email"])
        )
    ).scalar_one()
    other.plan = "professional"
    other.credits = 100
    await db_session.flush()

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "product_scene",
            "prompt": "使用别人的图片作为参考",
            "reference_asset_ids": [reference_id],
            "quality_tier": "fast",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=other_headers,
    )

    assert response.status_code == 404
    assert "素材" in response.json()["detail"]


@pytest.mark.asyncio
async def test_idempotency_key_reuses_same_task(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    await _prepare_user(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)
    payload = {
        "mode": "free_creation",
        "prompt": "一张极简产品广告背景",
        "quality_tier": "fast",
        "idempotency_key": str(uuid.uuid4()),
    }

    first = await client.post(
        "/api/v1/images/generate",
        json=payload,
        headers=auth_headers,
    )
    second = await client.post(
        "/api/v1/images/generate",
        json=payload,
        headers=auth_headers,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["task_id"] == second.json()["task_id"]
    count = (
        await db_session.execute(
            select(func.count(ImageGenerationTask.id)).where(
                ImageGenerationTask.idempotency_key == payload["idempotency_key"]
            )
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_legacy_generate_request_keeps_three_credit_behavior(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    await _prepare_user(db_session)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(images_router, "_execute_image_task", _noop_execute)

    response = await client.post(
        "/api/v1/images/generate",
        json={"prompt": "legacy product photo", "num_outputs": 1},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    task = await db_session.get(
        ImageGenerationTask,
        uuid.UUID(response.json()["task_id"]),
    )
    assert task.mode == "legacy"
    assert task.credits_cost == 3


@pytest.mark.asyncio
async def test_product_scene_without_reference_provider_fails_explicitly(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    await _prepare_user(db_session)
    reference_id = await _upload_asset(client, auth_headers, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "")
    monkeypatch.setattr(settings, "REPLICATE_IMAGE_REFERENCE_MODEL", "")

    response = await client.post(
        "/api/v1/images/generate",
        json={
            "mode": "product_scene",
            "prompt": "保持商品一致并生成场景",
            "reference_asset_ids": [reference_id],
            "quality_tier": "standard",
            "idempotency_key": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "参考图" in response.json()["detail"]
