"""三入口共享的视频质量、风格和 H3 提示词引擎。"""

import pytest

from app.services.video_quality import (
    compile_i2va_prompt,
    compile_ref2va_prompt,
    get_style_preset,
    get_video_target_size,
    list_quality_tiers,
    list_style_presets,
    resolve_quality_tier,
)


def test_quality_tiers_control_model_resolution_and_credits():
    assert [item["id"] for item in list_quality_tiers()] == [
        "draft",
        "standard",
        "cinematic",
    ]

    standard = resolve_quality_tier("standard")
    assert standard["model"] == "MiniMax-H3-Highspeed"
    assert standard["resolution"] == "768P"
    assert standard["provider"] == "minimax"
    assert standard["credits_per_second"] == 15

    cinematic = resolve_quality_tier("cinematic")
    assert cinematic["model"] == "MiniMax-H3"
    assert cinematic["resolution"] == "2K"
    assert cinematic["credits_per_second"] == 24

    with pytest.raises(ValueError, match="质量档位"):
        resolve_quality_tier("unknown")


def test_style_presets_have_concrete_director_constraints():
    presets = list_style_presets()
    assert {item["id"] for item in presets} >= {
        "premium_luxury",
        "authentic_lifestyle",
        "cinematic_story",
        "commerce_showcase",
        "festive_warmth",
        "reference_match",
    }
    premium = get_style_preset("premium_luxury")
    assert "soft directional light" in premium["prompt"]
    assert "slow push-in" in premium["prompt"]

    with pytest.raises(ValueError, match="风格"):
        get_style_preset("unknown")


def test_compile_i2va_prompt_uses_official_h3_sections():
    prompt = compile_i2va_prompt(
        product_name="DONMIS 礼盒",
        direction="一只手打开礼盒，露出香薰片",
        duration=4,
        style_id="premium_luxury",
        template_direction="Premium product hero shot",
    )

    assert "at 0.00 seconds" in prompt
    assert "integrated_multimodal_description:" in prompt
    assert "[Shot 1]" in prompt
    assert "overall_soundscape:" in prompt
    assert "non_diegetic_music:" in prompt
    assert "一只手打开礼盒" in prompt
    assert "PRODUCT CONSISTENCY LOCK" in prompt


def test_compile_ref2va_prompt_uses_six_reference_sections():
    prompt = compile_ref2va_prompt(
        product_name="DONMIS 礼盒",
        direction="礼盒在圣诞树下缓慢旋转",
        duration=4,
        style_id="festive_warmth",
        reference_assets=[
            {"asset_id": "a", "role": "front", "is_primary": True},
            {"asset_id": "b", "role": "package", "is_primary": False},
        ],
        previous_title="准备包装材料",
        next_title="收尾微笑",
    )

    for section in (
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ):
        assert section in prompt
    assert "<Picture 1>" in prompt
    assert "fully_preserved" in prompt
    assert "准备包装材料" in prompt
    assert "收尾微笑" in prompt


def test_target_size_follows_quality_resolution():
    assert get_video_target_size("480P") == (480, 854)
    assert get_video_target_size("768P") == (768, 1366)
    assert get_video_target_size("2K") == (1440, 2560)
