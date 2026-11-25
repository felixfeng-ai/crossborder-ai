"""跨渠道营销活动方案的确定性测试。"""

import pytest

from app.services.marketing_campaign_plan import (
    build_fallback_marketing_campaign_plan,
    generate_marketing_campaign_plan,
    normalize_marketing_campaign_plan,
    render_marketing_campaign_plan_markdown,
)


def _fallback():
    return build_fallback_marketing_campaign_plan(
        product_name="宠物智能床",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="zh",
        campaign_goal="提升新品首周转化",
    )


def test_fallback_marketing_campaign_plan_is_executable_and_honest():
    """降级方案必须可执行，同时明确没有验证过的商品参数。"""

    plan = _fallback()

    assert plan["product_name"] == "宠物智能床"
    assert plan["platform"] == "TikTok"
    assert plan["metrics"]
    assert plan["launch_steps"]
    assert any("参数" in item for item in plan["assumptions"])
    assert "保证" not in plan["positioning"]


def test_normalize_campaign_plan_keeps_required_shape():
    """模型输出字段漂移时必须回落为稳定结构。"""

    fallback = _fallback()
    plan = normalize_marketing_campaign_plan(
        {
            "title": "宠物智能床首发方案",
            "audience": "美国宠物主",
            "value_props": ["舒适场景"],
            "channel_plan": [
                {
                    "channel": "TikTok",
                    "role": "引流",
                    "formats": ["短视频"],
                    "cadence": "每周三条",
                }
            ],
        },
        fallback=fallback,
    )

    assert plan["title"] == "宠物智能床首发方案"
    assert plan["audience"] == "美国宠物主"
    assert plan["value_props"] == ["舒适场景"]
    assert plan["launch_steps"] == fallback["launch_steps"]
    assert plan["channel_plan"][0]["formats"] == ["短视频"]


@pytest.mark.asyncio
async def test_invalid_model_json_falls_back_without_failing():
    """模型格式错误不能把营销方案任务变成失败。"""

    async def invalid_generator(*args, **kwargs):
        return "not a json plan"

    plan = await generate_marketing_campaign_plan(
        product_name="宠物智能床",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="zh",
        campaign_goal="提升转化",
        text_generator=invalid_generator,
    )

    assert plan["product_name"] == "宠物智能床"
    assert plan["metrics"]


def test_render_campaign_plan_contains_actionable_sections():
    """对话摘要必须包含让用户继续执行的关键部分。"""

    markdown = render_marketing_campaign_plan_markdown(_fallback())

    assert "目标人群" in markdown
    assert "渠道与内容" in markdown
    assert "发布步骤" in markdown
    assert "衡量指标" in markdown
