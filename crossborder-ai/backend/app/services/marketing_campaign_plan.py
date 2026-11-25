"""营销活动方案生成与展示。

本模块不依赖商品图片或视频首帧，先从商品名、目标平台和市场生成可执行的
跨渠道方案；用户后续再决定生成图片、视频或广告文案。
"""

import json
import re
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings
from app.services import provider_config
from app.services.ai.deepseek import DeepSeekService


PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "meta": "Meta",
    "amazon": "Amazon",
    "shopify": "Shopify",
}
OBJECTIVE_LABELS = {
    "conversion": "促进成交",
    "traffic": "获取流量",
    "launch": "新品发布",
    "retention": "复购召回",
}


def _clean_text(value: Any, fallback: str = "", limit: int = 500) -> str:
    text = str(value or "").strip()
    return (text or fallback)[:limit]


def _clean_list(value: Any, fallback: list[str], limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [
        str(item).strip()[:300]
        for item in value
        if str(item).strip()
    ]
    return cleaned[:limit] or fallback


def _extract_json_object(raw: str) -> dict[str, Any]:
    fenced = re.sub(r"```(?:json)?\s*(.*?)```", r"\1", raw or "", flags=re.I | re.S)
    match = re.search(r"\{.*\}", fenced, flags=re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group())
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_fallback_marketing_campaign_plan(
    *,
    product_name: str,
    objective: str,
    platform: str,
    market: str,
    language: str,
    campaign_goal: str,
) -> dict[str, Any]:
    """模型不可用时，生成不编造商品参数的可执行基础方案。"""

    product = _clean_text(product_name, "商品", 120)
    platform_id = platform if platform in PLATFORM_LABELS else "tiktok"
    platform_label = PLATFORM_LABELS[platform_id]
    objective_id = objective if objective in OBJECTIVE_LABELS else "conversion"
    objective_label = OBJECTIVE_LABELS[objective_id]
    target_market = _clean_text(market, "US", 40)
    goal = _clean_text(
        campaign_goal,
        "通过场景化内容建立商品认知并提升目标平台转化",
        500,
    )

    return {
        "title": f"{product} · {target_market} {platform_label} 营销方案",
        "product_name": product,
        "objective": objective_label,
        "platform": platform_label,
        "market": target_market,
        "language": _clean_text(language, "zh", 20),
        "audience": (
            f"{target_market} 市场中正在比较同类商品、关注实际使用体验和"
            f"购买决策效率的潜在买家"
        ),
        "positioning": (
            f"围绕「{product}」的真实使用场景建立清晰价值，"
            "用可验证的商品信息和场景化表达减少购买犹豫。"
        ),
        "campaign_goal": goal,
        "value_props": [
            "用真实使用场景解释商品价值，而不是堆砌形容词",
            "只表达商品资料中可以验证的卖点、材质和功能",
            "统一短视频、图片和文案的行动号召，减少信息断层",
        ],
        "channel_plan": [
            {
                "channel": platform_label,
                "role": "获取注意力并承接首轮转化",
                "formats": ["15 秒场景短视频", "商品主图", "广告文案 A/B"],
                "cadence": "首周发布 3 组内容，按点击与转化复盘后迭代",
            }
        ],
        "content_plan": [
            {
                "stage": "场景预热",
                "assets": ["痛点场景图", "商品主图"],
                "message": "先让目标买家识别自己的使用场景",
            },
            {
                "stage": "卖点验证",
                "assets": ["15 秒短视频", "细节图"],
                "message": "用真实商品细节和使用过程建立可信度",
            },
            {
                "stage": "转化收口",
                "assets": ["广告文案 A/B", "行动号召画面"],
                "message": "保留有效表达，集中承接点击和加购",
            },
        ],
        "launch_steps": [
            "确认商品资料、目标国家、预算和投放账户",
            "补齐商品主图与至少 3 张真实参考素材",
            "制作 3 组短视频/图片/文案组合并完成平台合规检查",
            "小预算测试后保留高点击版本，淘汰低效素材",
            "按点击率、加购率和转化成本决定是否扩量",
        ],
        "metrics": [
            "曝光量",
            "点击率 CTR",
            "加购率",
            "转化率 CVR",
            "单次转化成本",
            "广告投入产出比 ROAS",
        ],
        "assumptions": [
            "目标平台、市场、预算和具体商品参数仍需以真实活动配置为准",
            "方案不包含未经验证的价格、折扣、认证或性能承诺",
            "生成图片或视频前需要选择商品参考素材",
        ],
    }


def normalize_marketing_campaign_plan(
    payload: dict[str, Any],
    *,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """把模型输出收敛到前端可稳定渲染的方案结构。"""

    if not isinstance(payload, dict):
        return fallback
    result = dict(fallback)
    for key in (
        "title",
        "product_name",
        "objective",
        "platform",
        "market",
        "language",
        "audience",
        "positioning",
        "campaign_goal",
    ):
        result[key] = _clean_text(payload.get(key), str(fallback.get(key) or ""))
    result["value_props"] = _clean_list(
        payload.get("value_props"),
        fallback["value_props"],
    )

    channel_plan = payload.get("channel_plan")
    if isinstance(channel_plan, list):
        normalized_channels = []
        for item in channel_plan[:5]:
            if not isinstance(item, dict):
                continue
            normalized_channels.append({
                "channel": _clean_text(item.get("channel"), "", 100),
                "role": _clean_text(item.get("role"), "", 300),
                "formats": _clean_list(item.get("formats"), [], 8),
                "cadence": _clean_text(item.get("cadence"), "", 300),
            })
        if normalized_channels:
            result["channel_plan"] = normalized_channels

    content_plan = payload.get("content_plan")
    if isinstance(content_plan, list):
        normalized_content = []
        for item in content_plan[:6]:
            if not isinstance(item, dict):
                continue
            normalized_content.append({
                "stage": _clean_text(item.get("stage"), "", 100),
                "assets": _clean_list(item.get("assets"), [], 8),
                "message": _clean_text(item.get("message"), "", 400),
            })
        if normalized_content:
            result["content_plan"] = normalized_content

    result["launch_steps"] = _clean_list(
        payload.get("launch_steps"),
        fallback["launch_steps"],
        10,
    )
    result["metrics"] = _clean_list(
        payload.get("metrics"),
        fallback["metrics"],
        10,
    )
    result["assumptions"] = _clean_list(
        payload.get("assumptions"),
        fallback["assumptions"],
        10,
    )
    return result


async def generate_marketing_campaign_plan(
    *,
    product_name: str,
    objective: str,
    platform: str,
    market: str,
    language: str,
    campaign_goal: str,
    text_generator: Optional[Callable[..., Awaitable[str]]] = None,
) -> dict[str, Any]:
    """优先使用模型生成方案，失败时返回确定性降级方案。"""

    fallback = build_fallback_marketing_campaign_plan(
        product_name=product_name,
        objective=objective,
        platform=platform,
        market=market,
        language=language,
        campaign_goal=campaign_goal,
    )
    api_key = provider_config.get(
        "deepseek",
        "api_key",
        settings.DEEPSEEK_API_KEY or "",
    )
    if text_generator is None and not api_key:
        return fallback

    generator = text_generator or DeepSeekService().generate
    system_prompt = (
        "You are a senior cross-border ecommerce marketing strategist. "
        "Return ONLY valid JSON with keys title, product_name, objective, platform, "
        "market, language, audience, positioning, campaign_goal, value_props, "
        "channel_plan, content_plan, launch_steps, metrics, assumptions. "
        "Use only supplied facts. Do not invent product specifications, prices, "
        "discounts, certifications, customer reviews or performance results."
    )
    user_prompt = (
        f"Product: {product_name}\nObjective: {objective}\nPlatform: {platform}\n"
        f"Market: {market}\nLanguage: {language}\nCampaign goal: {campaign_goal}\n"
        "Create a concise, executable campaign plan covering audience, positioning, "
        "core messages, channel plan, content stages, launch steps and metrics. "
        "State missing facts in assumptions instead of inventing them."
    )
    try:
        raw = await generator(
            system_prompt,
            user_prompt,
            max_tokens=2200,
            temperature=0.5,
        )
        payload = _extract_json_object(raw)
        return normalize_marketing_campaign_plan(payload, fallback=fallback)
    except Exception:
        return fallback


def render_marketing_campaign_plan_markdown(plan: dict[str, Any]) -> str:
    """把方案渲染为 Agent 对话可直接阅读的 Markdown。"""

    lines = [
        f"## {plan['title']}",
        "",
        f"**目标**：{plan['objective']}  ",
        f"**平台**：{plan['platform']} · **市场**：{plan['market']}",
        "",
        f"### 目标人群\n{plan['audience']}",
        "",
        f"### 定位\n{plan['positioning']}",
        "",
        "### 核心信息",
        *[f"- {item}" for item in plan["value_props"]],
        "",
        "### 渠道与内容",
    ]
    for item in plan["channel_plan"]:
        formats = "、".join(item["formats"])
        lines.append(
            f"- **{item['channel']}**：{item['role']}；形式：{formats}；节奏：{item['cadence']}"
        )
    for item in plan["content_plan"]:
        lines.append(
            f"- **{item['stage']}**：{'、'.join(item['assets'])}；{item['message']}"
        )
    lines.extend([
        "",
        "### 发布步骤",
        *[f"{index}. {item}" for index, item in enumerate(plan["launch_steps"], 1)],
        "",
        f"### 衡量指标\n{' · '.join(plan['metrics'])}",
        "",
        f"### 前提\n{'；'.join(plan['assumptions'])}",
    ])
    return "\n".join(lines)
