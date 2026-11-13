"""Qwen3-VL IP 图片初筛适配器测试。"""

import json

import pytest

from app.models.image_asset import ImageAsset
from app.services import ip_vision


def _asset(tmp_path, storage_key="user/visual.png") -> ImageAsset:
    path = tmp_path / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-image")
    return ImageAsset(
        user_id="00000000-0000-0000-0000-000000000001",
        name="visual.png",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=800,
        height=800,
        file_size=10,
    )


def test_vision_config_is_optional(monkeypatch):
    monkeypatch.setattr(ip_vision.provider_config, "get", lambda *args: "")
    assert ip_vision.get_vision_config() is None


@pytest.mark.asyncio
async def test_analyze_image_asset_parses_structured_vision_response(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(ip_vision.settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(
        ip_vision.provider_config,
        "get",
        lambda provider, field, default=None: {
            "api_key": "test-key",
            "vision_model": "qwen3-vl-plus",
        }.get(field, default or ""),
    )
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            content = json.dumps(
                {
                    "items": [
                        {
                            "type": "logo",
                            "label": "Nike",
                            "confidence": 0.91,
                            "bbox": [100, 200, 300, 400],
                        }
                    ]
                }
            )
            return {"choices": [{"message": {"content": content}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr(ip_vision.httpx, "AsyncClient", FakeClient)

    items = await ip_vision.analyze_image_asset(_asset(tmp_path))

    assert items[0]["label"] == "Nike"
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "qwen3-vl-plus"


def test_visual_items_cover_watermark_character_and_missing_bbox():
    risks = ip_vision.visual_items_to_risks(
        [
            {
                "type": "watermark",
                "label": "stock",
                "confidence": 0.8,
                "bbox": [1, 2, 3, 4],
            },
            {
                "type": "character",
                "label": "cartoon character",
                "confidence": 0.7,
                "bbox": None,
            },
        ],
        asset_id="asset-1",
    )

    assert {item["category"] for item in risks} == {
        "watermark",
        "character_ip",
    }
    assert any(item["code"] == "VISION_REGION_UNVERIFIED" for item in risks)


def test_visual_items_downgrade_authorized_brand():
    risks = ip_vision.visual_items_to_risks(
        [
            {
                "type": "logo",
                "label": "Nike",
                "confidence": 0.95,
                "bbox": [10, 10, 20, 20],
            }
        ],
        asset_id="asset-1",
        authorized_brands={"Nike"},
    )

    assert risks[0]["severity"] == "info"
