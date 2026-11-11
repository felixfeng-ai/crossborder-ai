"""AI 营销视频 Agent：把想法转换为结构化 Brief 与分镜。"""

import json
import re
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings
from app.services import provider_config
from app.services.ai.deepseek import DeepSeekService
from app.services.minimax_video import PRODUCT_LOCK_PROMPT, estimate_video_credits


PLATFORM_OPTIONS = (
    {"id": "tiktok", "name": "TikTok / Reels / Shorts", "ratio": "9:16"},
    {"id": "shopify_ads", "name": "Shopify 广告", "ratio": "9:16"},
    {"id": "marketplace", "name": "通用电商详情页", "ratio": "9:16"},
)

MARKETING_TEMPLATES = (
    {
        "id": "presenter_demo",
        "name": "人物演示",
        "description": "AI 品牌演示者手持商品，突出使用场景和卖点。",
    },
    {
        "id": "problem_solution",
        "name": "痛点解决",
        "description": "先呈现使用痛点，再展示商品如何解决问题。",
    },
    {
        "id": "unboxing",
        "name": "开箱展示",
        "description": "从包装、开箱到细节展示，适合新品和礼盒。",
    },
    {
        "id": "feature_focus",
        "name": "卖点聚焦",
        "description": "用近景和镜头运动快速说明材质、结构与核心功能。",
    },
)

_SHOT_COUNTS = {15: 3, 20: 4, 30: 5}


def _split_durations(total: int, count: int) -> list[int]:
    """把总时长均匀分配到镜头，并保证每个镜头至少 4 秒。"""
    base = total // count
    remainder = total % count
    values = [base + (1 if index < remainder else 0) for index in range(count)]
    return [max(4, value) for value in values]


def _template_shot_blueprints(template_id: str) -> list[tuple[str, str, str]]:
    """返回模板对应的 (标题, 目的, 画面指令) 列表。"""
    lock = f"\n\n{PRODUCT_LOCK_PROMPT}"
    if template_id == "problem_solution":
        return [
            (
                "痛点钩子",
                "hook",
                "Start with the everyday problem. Keep the product out of focus, then reveal it as the solution.",
            ),
            (
                "解决方案",
                "presenter",
                "An AI-generated brand presenter introduces and holds the product naturally, explaining the benefit without claiming to be a real customer.",
            ),
            (
                "使用效果",
                "proof",
                "Close product demonstration and real texture or structural detail. Do not invent performance results.",
            ),
            (
                "行动号召",
                "cta",
                "Clean end frame with the product centered and clear negative space for a short call to action.",
            ),
            (
                "补充卖点",
                "benefit",
                "A second concise benefit shot with smooth camera movement and realistic lighting.",
            ),
        ]
    if template_id == "unboxing":
        return [
            (
                "包装亮相",
                "hook",
                "Show the package in a real desk or doorway scene, premium lighting, no extra logos.",
            ),
            (
                "开箱动作",
                "hands",
                "Hands open the package and reveal the product. Keep hands anatomically natural and the package unchanged.",
            ),
            (
                "产品细节",
                "detail",
                "Macro detail shot of material, cap, surface and label with controlled reflections.",
            ),
            (
                "使用场景",
                "demo",
                "An AI-generated brand presenter uses the product in a believable everyday setting, not as a real-customer testimonial.",
            ),
            (
                "行动号召",
                "cta",
                "Final hero frame with product centered and space for a short CTA.",
            ),
        ]
    if template_id == "feature_focus":
        return [
            (
                "视觉钩子",
                "hook",
                "Fast but smooth macro push-in on the product with a strong material highlight.",
            ),
            (
                "核心卖点",
                "feature",
                "Show one functional feature through motion and light. Do not add features not visible in the reference.",
            ),
            (
                "人物演示",
                "presenter",
                "An AI-generated brand presenter holds the product and demonstrates the feature without testimonial claims.",
            ),
            (
                "细节证明",
                "detail",
                "Close-up proof of structure, texture and finish with stable product geometry.",
            ),
            (
                "行动号召",
                "cta",
                "Clean product end frame, subtle camera settle and negative space for CTA.",
            ),
        ]
    return [
        (
            "开场钩子",
            "hook",
            "Confident opening hero shot with the product immediately recognizable and a strong visual hook.",
        ),
        (
            "人物演示",
            "presenter",
            "An AI-generated brand presenter holds and uses the product naturally in a lifestyle setting. Presenter is not a real-customer testimonial.",
        ),
        (
            "细节证明",
            "detail",
            "Close-up detail of material, logo, package and structure with realistic light and no morphing.",
        ),
        (
            "价值总结",
            "benefit",
            "Show the practical benefit through a short demonstration and stable product shape.",
        ),
        (
            "行动号召",
            "cta",
            "Final clean product frame with negative space for a concise call to action.",
        ),
    ]


def _select_blueprints(
    blueprints: list[tuple[str, str, str]],
    count: int,
) -> list[tuple[str, str, str]]:
    """控制镜头数时始终保留开场与 CTA。"""
    if count >= len(blueprints):
        return blueprints
    if count <= 1:
        return blueprints[:1]
    middle = blueprints[1:-1][: count - 2]
    return [blueprints[0], *middle, blueprints[-1]]


def build_fallback_marketing_plan(
    *,
    idea: str,
    product_name: str,
    platform: str,
    market: str,
    language: str,
    duration: int,
    template_id: str,
) -> dict[str, Any]:
    """在 LLM 不可用时生成稳定、可执行的基础营销方案。"""
    shot_count = _SHOT_COUNTS.get(duration, 3)
    durations = _split_durations(duration, shot_count)
    blueprints = _select_blueprints(
        _template_shot_blueprints(template_id),
        shot_count,
    )
    product = product_name.strip() or "the product"
    shot_subject = f"{product} for {market} shoppers"
    lock = f"\n\n{PRODUCT_LOCK_PROMPT}"
    shots = []
    for index, (title, purpose, direction) in enumerate(blueprints):
        shots.append(
            {
                "position": index + 1,
                "title": title,
                "purpose": purpose,
                "duration": durations[index],
                "prompt": (
                    f"{direction} Product: {shot_subject}. Marketing idea: {idea.strip()}. "
                    f"Platform: {platform}. Target language: {language}. "
                    "No fake testimonial, no invented price or unsupported performance claim."
                    f"{lock}"
                ),
            }
        )

    return {
        "title": f"{product_name} · {market} 营销短视频",
        "audience": f"{market} market shoppers interested in {product_name}",
        "angle": idea.strip() or "product demonstration",
        "hook": "Show the product's most recognizable benefit in the first two seconds.",
        "script": (
            f"Introduce {product_name}, demonstrate one practical benefit, "
            "and finish with a clear call to action."
        ),
        "cta": "Discover the product",
        "shots": shots,
    }


def _extract_json_object(raw: str) -> dict[str, Any]:
    fenced = re.sub(r"```(?:json)?\s*(.*?)```", r"\1", raw, flags=re.I | re.S)
    match = re.search(r"\{.*\}", fenced, flags=re.S)
    if not match:
        raise ValueError("营销方案没有返回 JSON")
    payload = json.loads(match.group())
    if not isinstance(payload, dict):
        raise ValueError("营销方案格式错误")
    return payload


def parse_marketing_plan(raw: str) -> dict[str, Any]:
    """解析并规范化 LLM 返回的营销方案。"""
    payload = _extract_json_object(raw)
    required_text = ("title", "audience", "angle", "hook", "script", "cta")
    for field in required_text:
        if not str(payload.get(field) or "").strip():
            raise ValueError(f"营销方案缺少 {field}")

    shots = payload.get("shots")
    if not isinstance(shots, list) or len(shots) < 3 or len(shots) > 5:
        raise ValueError("营销方案必须包含 3-5 个分镜")

    normalized = []
    for item in sorted(shots, key=lambda value: int(value.get("position", 0))):
        if not isinstance(item, dict):
            raise ValueError("分镜格式错误")
        title = str(item.get("title") or "").strip()
        purpose = str(item.get("purpose") or "scene").strip()
        prompt = str(item.get("prompt") or "").strip()
        duration = int(item.get("duration") or 5)
        if not title or not prompt:
            raise ValueError("分镜缺少标题或画面描述")
        duration = max(4, min(15, duration))
        if "PRODUCT CONSISTENCY LOCK" not in prompt:
            prompt = f"{prompt}\n\n{PRODUCT_LOCK_PROMPT}"
        normalized.append(
            {
                "position": len(normalized) + 1,
                "title": title[:255],
                "purpose": purpose[:100],
                "prompt": prompt,
                "duration": duration,
            }
        )

    return {
        "title": str(payload["title"]).strip()[:255],
        "audience": str(payload["audience"]).strip(),
        "angle": str(payload["angle"]).strip(),
        "hook": str(payload["hook"]).strip(),
        "script": str(payload["script"]).strip(),
        "cta": str(payload["cta"]).strip(),
        "shots": normalized,
    }


def estimate_marketing_plan_credits(
    plan: dict[str, Any],
    *,
    model: str,
    resolution: str,
) -> int:
    """按分镜时长估算项目总积分。"""
    return sum(
        estimate_video_credits(model, resolution, int(shot["duration"]))
        for shot in plan.get("shots", [])
    )


async def generate_marketing_plan(
    *,
    idea: str,
    product_name: str,
    platform: str,
    market: str,
    language: str,
    duration: int,
    template_id: str,
    brand_context: Optional[str] = None,
    text_generator: Optional[Callable[..., Awaitable[str]]] = None,
) -> dict[str, Any]:
    """优先使用 DeepSeek 生成方案，失败时返回确定性降级方案。"""
    fallback = build_fallback_marketing_plan(
        idea=idea,
        product_name=product_name,
        platform=platform,
        market=market,
        language=language,
        duration=duration,
        template_id=template_id,
    )
    api_key = provider_config.get(
        "deepseek", "api_key", settings.DEEPSEEK_API_KEY or ""
    )
    if text_generator is None and not api_key:
        return fallback

    generator = text_generator or DeepSeekService().generate
    system_prompt = (
        "You are a senior cross-border ecommerce creative director. "
        "Return ONLY valid JSON with keys title, audience, angle, hook, script, cta, shots. "
        "shots must have 3-5 objects with position, title, purpose, prompt, duration. "
        "Prompts must lock product shape, color, material, logo and package text. "
        "AI presenters must never be described as real customers or testimonial evidence."
    )
    if brand_context:
        system_prompt = f"{brand_context}\n\n{system_prompt}"
    user_prompt = (
        f"Product: {product_name}\nIdea: {idea}\nPlatform: {platform}\n"
        f"Market: {market}\nLanguage: {language}\nDuration: {duration}s\n"
        f"Template: {template_id}\n"
        "Design a coherent multi-shot marketing video. Do not invent prices, discounts, "
        "certifications or performance results."
    )
    try:
        raw = await generator(
            system_prompt,
            user_prompt,
            max_tokens=2200,
            temperature=0.6,
        )
        plan = parse_marketing_plan(raw)
        expected_count = _SHOT_COUNTS.get(duration, len(plan["shots"]))
        total_duration = sum(shot["duration"] for shot in plan["shots"])
        if len(plan["shots"]) != expected_count or total_duration != duration:
            return fallback
        return plan
    except Exception:
        return fallback
