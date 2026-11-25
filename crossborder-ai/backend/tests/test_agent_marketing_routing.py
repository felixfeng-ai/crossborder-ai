"""营销工作区的工具路由回归测试。"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.agent_context import build_system_prompt
from app.services.ai import agent_orchestrator as orchestrator_module
from app.services.ai.agent_orchestrator import AgentOrchestrator


def _tool_names(tools: list[dict]) -> set[str]:
    return {
        str(item.get("function", {}).get("name") or "")
        for item in tools
    }


def test_marketing_plan_request_uses_marketing_tool_without_product_selection():
    """营销方案是营销任务，不应让模型自行进入选品分析。"""

    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )

    tools = orchestrator.tools_for_workspace(
        "给宠物智能床生成一个营销方案"
    )
    names = _tool_names(tools)

    assert "create_marketing_campaign_plan" in names
    assert "select_products" not in names
    assert "analyze_category" not in names


@pytest.mark.asyncio
async def test_run_react_passes_only_marketing_safe_tools(monkeypatch):
    """模型调用入口必须使用工作区过滤后的工具集。"""

    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )
    captured: dict = {}

    async def fake_chat(messages, tools=None, max_tokens=2000):
        captured["tools"] = tools or []
        return {"content": "营销方案已生成", "tool_calls": []}

    monkeypatch.setattr(orchestrator.llm, "chat_with_tools", fake_chat)

    await orchestrator.run_react("给宠物智能床生成一个营销方案")
    names = _tool_names(captured["tools"])

    assert "create_marketing_campaign_plan" in names
    assert "select_products" not in names
    assert "analyze_category" not in names


def test_explicit_market_request_restores_analysis_tools_in_marketing():
    """营销 Agent 不能吞掉用户明确提出的市场或选品判断。"""

    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )

    names = _tool_names(
        orchestrator.tools_for_workspace(
            "分析宠物智能床在美国市场的竞争和利润，值不值得做"
        )
    )

    assert "select_products" in names
    assert "analyze_category" in names
    assert "create_marketing_campaign_plan" in names


def test_target_market_wording_in_plan_does_not_enable_selection_tools():
    """营销方案提到目标市场时仍属于方案任务，不是市场分析。"""

    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )

    names = _tool_names(
        orchestrator.tools_for_workspace(
            "围绕美国目标市场给宠物智能床生成一个营销方案"
        )
    )

    assert "create_marketing_campaign_plan" in names
    assert "select_products" not in names
    assert "analyze_category" not in names


def test_general_workspace_keeps_existing_product_selection_tools():
    """通用 Agent 的选品能力保持不变。"""

    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="general",
    )

    names = _tool_names(
        orchestrator.tools_for_workspace("推荐一个适合美国市场的宠物用品")
    )

    assert "select_products" in names
    assert "analyze_category" in names


def test_marketing_prompt_requires_campaign_plan_tool_and_forbids_implicit_selection():
    """营销提示词必须给出确定性的工具选择边界。"""

    prompt = build_system_prompt("marketing")

    assert "create_marketing_campaign_plan" in prompt
    assert "不得调用 select_products" in prompt


@pytest.mark.asyncio
async def test_create_marketing_campaign_plan_works_without_asset(monkeypatch):
    """营销活动方案不能依赖视频首帧或已有活动。"""

    async def fake_generate_plan(**kwargs):
        return {
            "title": f"{kwargs['product_name']} 营销方案",
            "product_name": kwargs["product_name"],
            "objective": "促进成交",
            "platform": kwargs["platform"],
            "market": kwargs["market"],
            "language": kwargs["language"],
            "campaign_goal": kwargs["campaign_goal"],
            "audience": "关注宠物睡眠质量的美国买家",
            "positioning": "围绕舒适和易清洁建立清晰卖点",
            "value_props": ["舒适支撑", "清洁便利"],
            "channel_plan": [],
            "content_plan": [],
            "launch_steps": [],
            "metrics": ["CTR", "CVR", "ROAS"],
            "assumptions": ["具体材质和尺寸以真实商品资料为准"],
        }

    monkeypatch.setattr(
        orchestrator_module,
        "generate_marketing_campaign_plan",
        fake_generate_plan,
    )
    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )

    result = await orchestrator._execute_step(
        "create_marketing_campaign_plan",
        {
            "product_name": "宠物智能床",
            "platform": "tiktok",
            "market": "US",
        },
    )

    assert result["status"] == "success"
    assert result["data"]["plan"]["product_name"] == "宠物智能床"
    assert "营销方案" in result["summary"]


@pytest.mark.asyncio
async def test_marketing_rejects_unavailable_selection_tool_call(monkeypatch):
    """模型幻觉返回未开放工具时，执行层必须拒绝而不是偷偷做选品。"""

    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )
    call_count = {"value": 0}

    async def fake_chat(messages, tools=None, max_tokens=2000):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "select_products",
                            "arguments": '{"keyword":"宠物智能床"}',
                        },
                    }
                ],
            }
        return {"content": "已改为生成营销方案", "tool_calls": []}

    async def forbidden_execute(*args, **kwargs):
        raise AssertionError("未开放的选品工具不应被执行")

    monkeypatch.setattr(orchestrator.llm, "chat_with_tools", fake_chat)
    monkeypatch.setattr(orchestrator, "_execute_timed_tool", forbidden_execute)

    result = await orchestrator.run_react("给宠物智能床生成一个营销方案")

    assert result["steps"][0]["status"] == "failed"
    assert "营销工作区" in result["steps"][0]["error"]


@pytest.mark.asyncio
async def test_bound_campaign_context_overrides_model_product_guess(monkeypatch):
    """已有营销活动时，必须使用活动绑定商品而不是重新猜商品。"""

    workspace_id = uuid4()
    campaign = SimpleNamespace(
        id=uuid4(),
        product_id=uuid4(),
        objective="launch",
        platform="shopify",
        market="US",
        language="en",
        brief_json="{}",
    )
    product = SimpleNamespace(
        title="活动绑定的宠物智能床",
        url="https://example.com/product",
    )
    captured: dict = {}

    class FakeDb:
        async def execute(self, query):
            return self

        def scalar_one_or_none(self):
            return campaign

        async def get(self, model, item_id):
            return product

        async def flush(self):
            return None

    async def fake_generate_plan(**kwargs):
        captured.update(kwargs)
        return {
            "title": f"{kwargs['product_name']} 营销方案",
            "product_name": kwargs["product_name"],
            "objective": kwargs["objective"],
            "platform": kwargs["platform"],
            "market": kwargs["market"],
            "language": kwargs["language"],
            "campaign_goal": kwargs["campaign_goal"],
            "audience": "目标买家",
            "positioning": "真实活动定位",
            "value_props": ["真实卖点"],
            "channel_plan": [],
            "content_plan": [],
            "launch_steps": [],
            "metrics": ["CTR"],
            "assumptions": ["以活动配置为准"],
        }

    monkeypatch.setattr(
        orchestrator_module,
        "generate_marketing_campaign_plan",
        fake_generate_plan,
    )
    orchestrator = AgentOrchestrator(
        user=SimpleNamespace(id=uuid4()),
        db=FakeDb(),
        workspace="marketing",
        campaign_id=str(campaign.id),
        workspace_id=workspace_id,
    )

    result = await orchestrator._execute_step(
        "create_marketing_campaign_plan",
        {
            "product_name": "模型猜错的商品",
            "objective": "traffic",
            "platform": "meta",
            "market": "UK",
            "language": "fr",
        },
    )

    assert result["status"] == "success"
    assert captured["product_name"] == "活动绑定的宠物智能床"
    assert captured["objective"] == "launch"
    assert captured["platform"] == "shopify"
    assert captured["market"] == "US"
    brief = json.loads(campaign.brief_json)
    assert brief["agent_campaign_plan"]["plan"]["product_name"] == "活动绑定的宠物智能床"


@pytest.mark.asyncio
async def test_marketing_plan_round_executes_new_tool_and_returns_plan(monkeypatch):
    """营销方案请求的完整 ReAct 回合必须落到方案卡数据。"""

    async def fake_generate_plan(**kwargs):
        return {
            "title": f"{kwargs['product_name']} 营销方案",
            "product_name": kwargs["product_name"],
            "objective": "促进成交",
            "platform": "TikTok",
            "market": kwargs["market"],
            "language": kwargs["language"],
            "campaign_goal": kwargs["campaign_goal"],
            "audience": "美国宠物主",
            "positioning": "场景化展示",
            "value_props": ["真实场景"],
            "channel_plan": [],
            "content_plan": [],
            "launch_steps": ["确认素材"],
            "metrics": ["CTR"],
            "assumptions": ["参数以商品资料为准"],
        }

    monkeypatch.setattr(
        orchestrator_module,
        "generate_marketing_campaign_plan",
        fake_generate_plan,
    )
    orchestrator = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )
    call_count = {"value": 0}

    async def fake_chat(messages, tools=None, max_tokens=2000):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "plan-1",
                        "function": {
                            "name": "create_marketing_campaign_plan",
                            "arguments": json.dumps(
                                {
                                    "product_name": "宠物智能床",
                                    "objective": "conversion",
                                    "platform": "tiktok",
                                    "market": "US",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        return {"content": "营销方案已生成", "tool_calls": []}

    monkeypatch.setattr(orchestrator.llm, "chat_with_tools", fake_chat)

    result = await orchestrator.run_react("给宠物智能床生成一个营销方案")

    assert result["status"] == "success"
    assert result["summary"] == "营销方案已生成"
    assert result["steps"][0]["action"] == "create_marketing_campaign_plan"
    assert result["steps"][0]["data"]["plan"]["product_name"] == "宠物智能床"
