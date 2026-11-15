"""Replicate 多参考图请求契约测试。"""

import pytest

from app.services.ai.replicate import ReplicateService


@pytest.mark.asyncio
async def test_reference_image_uses_multiple_private_data_uris(monkeypatch):
    service = ReplicateService()
    service.api_key = "test-key"
    captured: dict = {}

    async def fake_run_prediction(model: str, input_data: dict):
        captured["model"] = model
        captured["input"] = input_data
        return ["https://cdn.example.com/reference-result.webp"]

    monkeypatch.setattr(service, "_run_prediction", fake_run_prediction)

    result = await service.generate_reference_image(
        prompt="保持商品一致，放入节日客厅",
        references=[
            (b"first-image", "image/png"),
            (b"second-image", "image/webp"),
        ],
        negative_prompt="变形，错误 logo",
        num_outputs=1,
        aspect_ratio="4:5",
        quality_tier="hd",
        reference_model="seedream-reference",
        reference_input_field="image_input",
    )

    assert result == ["https://cdn.example.com/reference-result.webp"]
    assert captured["model"] == "seedream-reference"
    assert len(captured["input"]["image_input"]) == 2
    assert captured["input"]["image_input"][0].startswith("data:image/png;base64,")
    assert "错误 logo" in captured["input"]["prompt"]
    assert captured["input"]["aspect_ratio"] == "4:5"
