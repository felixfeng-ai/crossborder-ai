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


def test_quality_resolution_respects_provider_bounds_and_aspect_ratio():
    from app.services.image_quality import resolve_image_resolution

    assert resolve_image_resolution("hd", "1:1") == "1440x1440"
    assert resolve_image_resolution("hd", "4:5") == "1152x1440"
    assert resolve_image_resolution("standard", "16:9") == "1280x720"


def test_aliyun_quality_tiers_route_to_pro_models(monkeypatch):
    from app.services.image_provider import get_image_provider

    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "aliyun-test-key")
    monkeypatch.setattr(settings, "ALIYUN_IMAGE_MODEL", "wanx2.1-t2i-turbo")
    provider = get_image_provider("aliyun")

    assert provider.model_for_quality("fast") == "wan2.2-t2i-flash"
    assert provider.model_for_quality("standard") == "wan2.2-t2i-plus"
    assert provider.model_for_quality("hd") == "wan2.2-t2i-plus"


def test_provider_capability_snapshot_never_exposes_secrets(monkeypatch):
    from app.services.image_provider import list_image_provider_capabilities

    monkeypatch.setattr(settings, "ALIYUN_DASHSCOPE_API_KEY", "secret-value")
    items = list_image_provider_capabilities()
    payload = str(items)

    assert {"aliyun", "replicate"} <= {item["provider"] for item in items}
    assert "secret-value" not in payload


def test_text_only_product_scene_provider_request_uses_free_creation_mode():
    from app.services.image_task_executor import _build_provider_request

    task = ImageGenerationTask(
        user_id=None,
        prompt="圣诞桌面摆件",
        mode="product_scene",
        quality_tier="standard",
        provider="seedream",
        aspect_ratio="1:1",
        reference_assets_json="[]",
        num_outputs=1,
        credits_cost=5,
        image_urls="[]",
    )

    request = _build_provider_request(
        task,
        prompt=task.prompt,
        num_outputs=1,
        references=[],
    )

    assert request.mode == "free_creation"


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


@pytest.mark.asyncio
async def test_executor_persists_actionable_provider_failure(
    db_session,
    monkeypatch,
):
    from app.services import image_task_executor

    user = User(
        email=f"provider-error-{uuid.uuid4().hex[:8]}@example.com",
        username="provider-error-user",
        password_hash="x",
        credits=100,
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()

    task = ImageGenerationTask(
        user_id=user.id,
        prompt="高清自由创作",
        mode="free_creation",
        quality_tier="hd",
        provider="aliyun",
        resolution="1440x1440",
        aspect_ratio="1:1",
        num_outputs=1,
        credits_cost=8,
        status="processing",
        image_urls="[]",
    )
    db_session.add(task)
    await db_session.flush()

    monkeypatch.setattr(
        image_task_executor.provider_config,
        "get",
        lambda group, key, default="": (
            "aliyun-test-key"
            if group == "aliyun" and key == "api_key"
            else default
        ),
    )

    async def fake_generate(self, request):
        raise RuntimeError(
            "Either width or height should be between 512 and 1440."
        )

    monkeypatch.setattr(
        "app.services.image_provider.AliyunImageProvider.generate",
        fake_generate,
    )

    await image_task_executor.run_image_generation(
        db_session,
        task.id,
        task.prompt,
        task.num_outputs,
    )

    await db_session.refresh(task)
    assert task.status == "failed"
    assert "尺寸" in task.error
    assert "Either width or height" not in task.error


@pytest.mark.asyncio
async def test_product_scene_auto_mode_falls_back_to_replicate(
    db_session,
    tmp_path,
    monkeypatch,
):
    from io import BytesIO

    from PIL import Image
    import app.services.image_task_executor as image_executor
    from app.services.image_provider import ImageProviderResult

    user = User(
        email=f"seedream-fallback-{uuid.uuid4().hex[:8]}@example.com",
        username="seedream-fallback",
        password_hash="x",
        credits=100,
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()

    storage_key = f"{user.id}/reference.png"
    target = tmp_path / storage_key
    target.parent.mkdir(parents=True)
    image_buffer = BytesIO()
    Image.new("RGB", (320, 320), (210, 90, 40)).save(
        image_buffer,
        format="PNG",
    )
    target.write_bytes(image_buffer.getvalue())
    asset = ImageAsset(
        user_id=user.id,
        name="商品参考图",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=320,
        height=320,
        file_size=target.stat().st_size,
    )
    db_session.add(asset)
    await db_session.flush()

    task = ImageGenerationTask(
        user_id=user.id,
        prompt="保持商品一致，生成冬季客厅",
        mode="product_scene",
        quality_tier="standard",
        provider="auto",
        resolution="1024x1280",
        aspect_ratio="4:5",
        reference_assets_json=json.dumps([str(asset.id)]),
        reference_coverage="provided",
        num_outputs=1,
        credits_cost=10,
        status="processing",
        image_urls="[]",
    )
    db_session.add(task)
    await db_session.flush()

    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SEEDREAM_API_KEY", "ark-test-key")
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "")
    monkeypatch.setattr(settings, "REPLICATE_API_KEY", "replicate-test-key")
    monkeypatch.setattr(
        settings,
        "REPLICATE_IMAGE_REFERENCE_MODEL",
        "bytedance/seedream-4",
    )
    provider_config.clear_cache()

    async def seedream_failure(self, request):
        raise ValueError("Seedream 服务暂不可用")

    async def replicate_success(self, request):
        output = BytesIO()
        Image.new("RGB", (320, 320), (20, 130, 80)).save(
            output,
            format="PNG",
        )
        return ImageProviderResult(
            urls=[],
            provider="replicate",
            model="bytedance/seedream-4",
            actual_cost_micros=120_000,
            local_outputs=[output.getvalue()],
        )

    monkeypatch.setattr(
        "app.services.image_provider.SeedreamImageProvider.generate",
        seedream_failure,
    )
    monkeypatch.setattr(
        "app.services.image_provider.ReplicateImageProvider.generate",
        replicate_success,
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
    assert task.model_used == "bytedance/seedream-4"
