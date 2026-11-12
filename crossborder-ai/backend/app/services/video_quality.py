"""三入口共享的视频质量档位、风格预设和 H3 提示词编译。"""

from typing import Any

from app.services.jimeng_video import (
    SEEDANCE_2_5,
    SEEDANCE_2_FAST,
    SEEDANCE_2_MINI,
    SEEDANCE_2_STANDARD,
)
from app.services.minimax_video import PRODUCT_LOCK_PROMPT


QUALITY_TIERS: tuple[dict[str, Any], ...] = (
    {
        "id": "draft",
        "name": "快速草稿",
        "description": "适合预览动作和构图，不建议直接投放。",
        "provider": "minimax",
        "model": "MiniMax-H3-Lite",
        "resolution": "480P",
        "credits_per_second": 8,
        "estimated_time_multiplier": 0.7,
    },
    {
        "id": "standard",
        "name": "标准商用",
        "description": "768P 商用画质，适合日常跨境内容生产。",
        "provider": "minimax",
        "model": "MiniMax-H3-Highspeed",
        "resolution": "768P",
        "credits_per_second": 15,
        "estimated_time_multiplier": 1.0,
    },
    {
        "id": "cinematic",
        "name": "电影级",
        "description": "2K 高细节输出，适合主视觉和品牌广告。",
        "provider": "minimax",
        "model": "MiniMax-H3",
        "resolution": "2K",
        "credits_per_second": 24,
        "estimated_time_multiplier": 1.7,
    },
    {
        "id": "seedance_mini",
        "name": "Seedance 极速草稿",
        "description": "2.0 Mini 480P，适合低成本试镜和批量草稿。",
        "provider": "jimeng",
        "model": SEEDANCE_2_MINI,
        "resolution": "480P",
        "credits_per_second": 5,
        "estimated_time_multiplier": 0.8,
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
    },
    {
        "id": "seedance_fast",
        "name": "Seedance 快速生成",
        "description": "2.0 Fast 720P，适合快速产出日常营销素材。",
        "provider": "jimeng",
        "model": SEEDANCE_2_FAST,
        "resolution": "720P",
        "credits_per_second": 15,
        "estimated_time_multiplier": 1.0,
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
    },
    {
        "id": "seedance",
        "name": "Seedance 标准商用",
        "description": "2.0 Standard 720P，当前默认的跨境营销主力档位。",
        "provider": "jimeng",
        "model": SEEDANCE_2_STANDARD,
        "resolution": "720P",
        "credits_per_second": 19,
        "estimated_time_multiplier": 1.2,
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
    },
    {
        "id": "seedance_1080",
        "name": "Seedance 高清",
        "description": "2.0 Standard 1080P，适合高清商品细节和品牌素材。",
        "provider": "jimeng",
        "model": SEEDANCE_2_STANDARD,
        "resolution": "1080P",
        "credits_per_second": 44,
        "estimated_time_multiplier": 1.5,
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
    },
    {
        "id": "seedance_25",
        "name": "Seedance 2.5 Pro",
        "description": "2.5 Pro 720P，适合长镜头、多素材参考和高质量营销。",
        "provider": "jimeng",
        "model": SEEDANCE_2_5,
        "resolution": "720P",
        "credits_per_second": 31,
        "estimated_time_multiplier": 1.8,
        "min_duration": 4,
        "max_duration": 30,
        "max_reference_images": 30,
        "supports_audio": True,
    },
    {
        "id": "seedance_25_1080",
        "name": "Seedance 2.5 Pro HD",
        "description": "2.5 Pro 1080P，适合品牌广告、长视频和高精度成片。",
        "provider": "jimeng",
        "model": SEEDANCE_2_5,
        "resolution": "1080P",
        "credits_per_second": 68,
        "estimated_time_multiplier": 2.2,
        "min_duration": 4,
        "max_duration": 30,
        "max_reference_images": 30,
        "supports_audio": True,
    },
)

STYLE_PRESETS: tuple[dict[str, str], ...] = (
    {
        "id": "premium_luxury",
        "name": "高端静奢",
        "description": "柔和侧光、低饱和、细腻材质和克制的镜头运动。",
        "prompt": (
            "Premium editorial product commercial, soft directional light, "
            "shallow depth of field, restrained contrast, refined material detail, "
            "slow push-in with small amplitude, clean and uncluttered composition."
        ),
        "music": "Sparse piano and sustained warm strings at a slow tempo.",
    },
    {
        "id": "authentic_lifestyle",
        "name": "真实生活",
        "description": "自然光、轻手持感和真实生活空间。",
        "prompt": (
            "Authentic lifestyle commercial, natural window light, realistic skin "
            "and household textures, gentle handheld camera movement, natural pacing, "
            "credible lived-in environment."
        ),
        "music": "Light acoustic guitar and soft room-tone-friendly percussion.",
    },
    {
        "id": "cinematic_story",
        "name": "电影叙事",
        "description": "电影级光影、明确景别和连贯动作。",
        "prompt": (
            "Cinematic live-action storytelling, layered motivated lighting, "
            "controlled highlights, subtle film grain, deliberate lens language, "
            "smooth continuity and measured camera movement."
        ),
        "music": "Low strings and sparse piano with a gradual dynamic build.",
    },
    {
        "id": "commerce_showcase",
        "name": "电商展示",
        "description": "主体清晰、高还原材质、动作稳定，适合直接转化。",
        "prompt": (
            "High-conversion ecommerce showcase, bright clean lighting, accurate "
            "product colors and material, stable geometry, limited camera motion, "
            "clear subject separation and practical space for captions."
        ),
        "music": "Clean electronic pulse with a light upbeat rhythm.",
    },
    {
        "id": "festive_warmth",
        "name": "节日氛围",
        "description": "暖色灯串、柔和光斑和温馨节日环境。",
        "prompt": (
            "Warm festive commercial, practical warm lights, soft glowing bokeh, "
            "balanced seasonal color palette, tactile materials, gentle cinematic "
            "camera movement and a cozy premium atmosphere."
        ),
        "music": "Soft bells, warm strings and a restrained holiday-inspired rhythm.",
    },
    {
        "id": "reference_match",
        "name": "参考图匹配",
        "description": "优先匹配已选商品图的构图、光线和色彩关系。",
        "prompt": (
            "Reference-led commercial direction, preserve the lighting direction, "
            "color relationships, composition logic and material response visible "
            "in the supplied product references without copying unrelated objects."
        ),
        "music": "Minimal ambient texture with restrained instrumental movement.",
    },
)

_QUALITY_BY_ID = {item["id"]: item for item in QUALITY_TIERS}
_STYLE_BY_ID = {item["id"]: item for item in STYLE_PRESETS}


def list_quality_tiers(
    configured_providers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """返回前端可见的质量档位副本。"""
    return [
        resolve_quality_tier(str(item["id"]))
        for item in QUALITY_TIERS
        if configured_providers is None
        or str(item["provider"]) in configured_providers
    ]


def list_style_presets() -> list[dict[str, str]]:
    """返回前端可见的风格预设副本。"""
    return [dict(item) for item in STYLE_PRESETS]


def resolve_quality_tier(tier_id: str) -> dict[str, Any]:
    """解析质量档位，并确保模型、分辨率和积分由服务端决定。"""
    tier = _QUALITY_BY_ID.get(tier_id)
    if tier is None:
        raise ValueError("视频质量档位不支持")
    return dict(tier)


def get_style_preset(style_id: str) -> dict[str, str]:
    """解析结构化风格预设。"""
    style = _STYLE_BY_ID.get(style_id)
    if style is None:
        raise ValueError("视频风格不支持")
    return dict(style)


def estimate_quality_credits(
    tier_id: str,
    duration: int,
) -> int:
    """按质量档位计算供应商实际渲染时长的积分。"""
    tier = resolve_quality_tier(tier_id)
    return max(1, int(tier["credits_per_second"]) * int(duration))


def get_video_target_size(resolution: str) -> tuple[int, int]:
    """返回 9:16 目标尺寸；保持偶数宽高，避免编码器兼容问题。"""
    sizes = {
        "480P": (480, 854),
        "720P": (720, 1280),
        "1080P": (1080, 1920),
        "768P": (768, 1366),
        "2K": (1440, 2560),
    }
    size = sizes.get(resolution)
    if size is None:
        raise ValueError("视频输出分辨率不支持")
    return size


def compile_i2va_prompt(
    *,
    product_name: str,
    direction: str,
    duration: int,
    style_id: str,
    template_direction: str = "",
    previous_title: str | None = None,
    next_title: str | None = None,
) -> str:
    """把首帧任务编译为 H3 I2VA 官方结构。"""
    style = get_style_preset(style_id)
    direction_text = _bounded_text(direction, 2400)
    template_text = _bounded_text(template_direction, 500)
    boundary = ""
    if previous_title:
        boundary += f" Continue naturally from the previous shot '{previous_title}'."
    if next_title:
        boundary += f" End with a composition compatible with '{next_title}'."
    return (
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        f"integrated_multimodal_description: [Shot 1] Live-action, {style['prompt']} "
        f"Product: {product_name}. {template_text} {direction_text}. "
        "Keep the exact product geometry, proportions, colors, packaging text, "
        "logo and material from <Picture 1>. Do not invent product parts or claims. "
        f"The shot lasts {int(duration)} seconds and ends in a stable product frame."
        f"{boundary}\n\n"
        "overall_soundscape: Quiet room ambience with subtle physical handling "
        "sounds that match the visible action. No dialogue, captions or watermark.\n\n"
        f"non_diegetic_music: {style['music']}\n\n"
        f"{PRODUCT_LOCK_PROMPT}"
    )


def compile_ref2va_prompt(
    *,
    product_name: str,
    direction: str,
    duration: int,
    style_id: str,
    reference_assets: list[dict[str, Any]],
    previous_title: str | None = None,
    next_title: str | None = None,
) -> str:
    """把多参考图镜头编译为 H3 Ref2VA 六段式结构。"""
    style = get_style_preset(style_id)
    if not reference_assets:
        raise ValueError("多参考图提示词至少需要一张图片")
    references = reference_assets[:9]
    subject_lines = []
    retention_lines = []
    for index, item in enumerate(references, start=1):
        role = str(item.get("role") or "detail")
        subject_lines.append(
            f"<Picture {index}> provides the product {role} view and must remain "
            f"the source for shape, color, material, label, logo and structure."
        )
        retention_lines.append(
            f"<Picture {index}>: fully_preserved - preserve the product {role} "
            "characteristics defined above."
        )

    boundary = ""
    if previous_title:
        boundary += f" Continue naturally from the previous shot '{previous_title}'."
    if next_title:
        boundary += f" End with an action and composition compatible with '{next_title}'."

    return (
        "subject_definitions:\n"
        + "\n".join(subject_lines)
        + "\n"
        "summary:\n"
        f"[reference generation] A {int(duration)}-second product shot of "
        f"{product_name}, using the supplied reference views to preserve one "
        f"consistent physical product. Style: {style['description']}\n"
        "retention_analysis:\n"
        + "\n".join(retention_lines)
        + "\n"
        "detailed_description:\n"
        f"The target video uses this visual direction: {style['prompt']} "
        f"[Shot 1] {_bounded_text(direction, 2400)}. Keep the product identical "
        "to the reference views; do not morph, melt, rebuild or redesign it."
        f"{boundary}\n"
        "overall_soundscape: Quiet room ambience with restrained physical product "
        "handling sounds matching the visible action.\n"
        f"non_diegetic_music: {style['music']}\n\n"
        f"{PRODUCT_LOCK_PROMPT}"
    )


def _bounded_text(value: str, limit: int) -> str:
    """限制单个提示词片段，避免超出供应商 7000 字符限制。"""
    return str(value or "").strip()[:limit]
