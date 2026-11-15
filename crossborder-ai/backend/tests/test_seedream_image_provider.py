"""火山方舟 Seedream 直连图片 Provider 契约测试。"""

import pytest

from app.core.config import settings
from app.models.image_generation_task import ImageGenerationTask
from app.services import provider_config


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_config.clear_cache()
    yield
    provider_config.clear_cache()


def test_seedream_request_uses_ark_image_api_and_reference_images():
    from app.services.ai.seedream_image import build_seedream_image_request

    request = build_seedream_image_request(
        api_key="ark-test-key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="doubao-seedream-4-0-250828",
        prompt="保持商品一致，放入圣诞客厅",
        reference_images=[(b"reference-png", "image/png")],
        quality_tier="hd",
    )

    assert request.url.endswith("/images/generations")
    assert request.headers["Authorization"] == "Bearer ark-test-key"
    assert request.body["model"] == "doubao-seedream-4-0-250828"
    assert request.body["size"] == "4K"
    assert request.body["sequential_image_generation"] == "disabled"
    assert request.body["watermark"] is False
    assert request.body["image"][0].startswith("data:image/png;base64,")


def test_seedream_provider_is_registered_for_product_scene(monkeypatch):
    from app.services.image_provider import get_image_provider

    monkeypatch.setattr(settings, "SEEDREAM_API_KEY", "ark-test-key")
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "")
    provider = get_image_provider("seedream")

    assert provider.is_configured() is True
    assert provider.supports("product_scene", "standard") is True
    assert provider.capabilities()["reference_images"] is True
    assert provider.capabilities()["max_reference_images"] == 14


@pytest.mark.asyncio
async def test_seedream_reuses_runtime_jimeng_ark_key(db_session):
    await provider_config.update_provider(
        db_session,
        "jimeng",
        {
            "api_key": "shared-ark-key",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "doubao-seedance-2-0-260128",
            "resolution": "720P",
        },
    )

    from app.services.ai.seedream_image import get_seedream_image_config

    config = get_seedream_image_config()
    assert config["api_key"] == "shared-ark-key"
    assert config["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"


def test_product_scene_provider_order_prefers_seedream_without_hardcoding():
    from app.services.image_task_executor import _provider_order

    task = ImageGenerationTask(
        user_id=None,
        prompt="商品场景",
        mode="product_scene",
        provider="auto",
        num_outputs=1,
        credits_cost=10,
        image_urls="[]",
    )

    assert _provider_order(task) == ["seedream", "replicate"]


@pytest.mark.asyncio
async def test_seedream_http_request_calls_ark_images_endpoint(monkeypatch):
    from app.services.ai import seedream_image

    monkeypatch.setattr(settings, "SEEDREAM_API_KEY", "ark-test-key")
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "")
    monkeypatch.setattr(
        settings,
        "SEEDREAM_BASE_URL",
        "https://ark.cn-beijing.volces.com/api/v3",
    )
    monkeypatch.setattr(
        settings,
        "SEEDREAM_IMAGE_MODEL",
        "doubao-seedream-4-0-250828",
    )
    captured: list[dict] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": [{"url": "https://cdn.example.com/seedream.png"}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, headers, json):
            captured.append(
                {
                    "url": url,
                    "headers": headers,
                    "body": json,
                }
            )
            return FakeResponse()

    monkeypatch.setattr(seedream_image.httpx, "AsyncClient", lambda **_: FakeClient())

    urls, model = await seedream_image.generate_seedream_images(
        prompt="保持商品一致，生成圣诞场景",
        reference_images=[(b"reference-png", "image/png")],
        quality_tier="hd",
        num_outputs=2,
    )

    assert urls == [
        "https://cdn.example.com/seedream.png",
        "https://cdn.example.com/seedream.png",
    ]
    assert model == "doubao-seedream-4-0-250828"
    assert len(captured) == 2
    assert captured[0]["url"].endswith("/images/generations")
    assert captured[0]["body"]["size"] == "4K"
    assert captured[0]["body"]["image"][0].startswith("data:image/png;base64,")
