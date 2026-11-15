"""图片 Provider 能力与参考图边界测试。"""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services import provider_config


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_config.clear_cache()
    yield
    provider_config.clear_cache()


def test_aliyun_provider_only_supports_text_to_image(monkeypatch):
    from app.services.image_provider import get_image_provider

    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "aliyun-test-key")
    provider = get_image_provider("aliyun")

    assert provider.is_configured() is True
    assert provider.supports("free_creation", "fast") is True
    assert provider.supports("product_scene", "fast") is False


def test_replicate_reference_requires_key_and_reference_model(monkeypatch):
    from app.services.image_provider import get_image_provider

    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "replicate-test-key")
    monkeypatch.setattr(settings, "REPLICATE_IMAGE_REFERENCE_MODEL", "")
    provider = get_image_provider("replicate")

    assert provider.is_configured() is True
    assert provider.supports("free_creation", "standard") is True
    assert provider.supports("product_scene", "standard") is False

    monkeypatch.setattr(
        settings,
        "REPLICATE_IMAGE_REFERENCE_MODEL",
        "seedream-reference",
    )
    provider_config.clear_cache()
    refreshed = get_image_provider("replicate")
    assert refreshed.supports("product_scene", "standard") is True


def test_provider_capability_snapshot_never_exposes_secrets(monkeypatch):
    from app.services.image_provider import list_image_provider_capabilities

    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "secret-value")
    items = list_image_provider_capabilities()
    payload = str(items)

    assert {"aliyun", "replicate"} <= {item["provider"] for item in items}
    assert "secret-value" not in payload


@pytest.mark.asyncio
async def test_executor_passes_private_references_to_product_scene_provider(
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.services.image_provider import ImageProviderResult
    import app.services.image_task_executor as image_executor

    user = User(
        email=f"provider-{uuid.uuid4().hex[:8]}@example.com",
        username="provider-user",
        password_hash="x",
        credits=100,
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()

    storage_key = f"{user.id}/reference.png"
    target = tmp_path / storage_key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"private-reference")
    asset = ImageAsset(
        user_id=user.id,
        name="商品参考图",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=320,
        height=320,
        file_size=17,
    )
    db_session.add(asset)
    await db_session.flush()

    task = ImageGenerationTask(
        user_id=user.id,
        prompt="保持商品一致，放入圣诞客厅",
        mode="product_scene",
        quality_tier="hd",
        provider="replicate",
        resolution="2048x2048",
        aspect_ratio="4:5",
        reference_assets_json=json.dumps([str(asset.id)]),
        reference_coverage="provided",
        num_outputs=1,
        credits_cost=12,
        status="processing",
        image_urls="[]",
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "replicate-test-key")
    monkeypatch.setattr(
        settings,
        "REPLICATE_IMAGE_REFERENCE_MODEL",
        "seedream-reference",
    )
    provider_config.clear_cache()

    captured = {}

    async def fake_generate(self, request):
        captured["request"] = request
        return ImageProviderResult(
            urls=["https://cdn.example.com/provider-result.webp"],
            provider="replicate",
            model="seedream-reference",
            actual_cost_micros=120_000,
        )

    async def fake_materialize(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "app.services.image_provider.ReplicateImageProvider.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        image_executor,
        "materialize_image_task_assets",
        fake_materialize,
    )

    await image_executor.run_image_generation(
        db_session,
        task.id,
        task.prompt,
        task.num_outputs,
    )

    await db_session.refresh(task)
    assert task.status == "completed"
    assert task.provider == "replicate"
    assert task.actual_cost_micros == 120_000
    assert captured["request"].references[0].data == b"private-reference"
    assert captured["request"].aspect_ratio == "4:5"
