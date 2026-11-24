"""Agent 图片提示词文字安全策略测试。"""

from app.services.ai.agent_orchestrator import AgentOrchestrator


def test_agent_image_prompt_removes_generated_copy_intent():
    from app.services.image_prompt_policy import prepare_agent_image_prompt

    prompt, negative = prepare_agent_image_prompt(
        "304不锈钢保温杯放在车载杯架，商品居中偏右，留左上角文案空间",
        mode="product_scene",
    )

    assert "留左上角文案空间" not in prompt
    assert "干净留白" in prompt
    assert "不得新增任何文字" in prompt
    assert "包装文字" in prompt
    assert "新增文字" in negative
    assert "乱码" in negative


def test_agent_image_prompt_does_not_duplicate_policy():
    from app.services.image_prompt_policy import prepare_agent_image_prompt

    prompt, negative = prepare_agent_image_prompt(
        "白色保温杯，商业摄影，干净留白，画面不得新增任何文字",
        mode="free_creation",
        negative_prompt="水印，字幕",
    )

    assert prompt.count("不得新增任何文字") == 1
    assert negative.count("新增文字") == 1
    assert "水印" in negative


def test_legacy_product_image_tool_is_marked_compatibility_only():
    tool = next(
        item
        for item in AgentOrchestrator.TOOLS
        if item["function"]["name"] == "generate_product_image"
    )
    description = tool["function"]["description"]

    assert "兼容旧客户端" in description
    assert "generate_image_asset" in description


def test_agent_system_prompt_forbids_model_rendered_marketing_copy():
    from app.services.agent_context import build_system_prompt

    prompt = build_system_prompt("marketing")
    assert "默认不生成任何文字" in prompt
    assert "模板" in prompt


def test_agent_system_prompt_limits_generic_selection_and_separates_history():
    from app.services.agent_context import build_system_prompt

    prompt = build_system_prompt("general")

    assert "泛化的同品类推荐只调用一次 select_products" in prompt
    assert "本次任务结果" in prompt
    assert "历史结果" in prompt
    assert "不得把历史结果写成累计执行次数" in prompt
