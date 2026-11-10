"""VeyaShip - Agent 结构化报告输出测试

验证两个报告工具（select_products / analyze_category）：
1. LLM 返回合法 JSON → 解析出 structured，report 由服务端模板渲染（合法 Markdown）
2. LLM 返回乱文本 → structured 为 None，report 为原始文本兜底（fail-open，不抛异常）
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.user import User
from app.services.ai.agent_orchestrator import (
    AgentOrchestrator,
    _extract_json,
    _render_report_markdown,
)
from app.services.ai.deepseek import DeepSeekService

VALID_JSON = (
    '{"market": {"monthly_search_volume": 126000, "active_listings": 48300, '
    '"avg_price_usd": 23.99, "head_concentration": 58, "competition_level": 4, '
    '"price_war_level": 3, "new_product_survival_rate": 32, '
    '"user_pains": ["佩戴滑落", "续航不足"]}, '
    '"products": [{"name": "开放式不入耳挂脖耳机", "suggested_price_usd": 29.99, '
    '"cost_cny": 42.0, "net_profit_usd": 6.2, "net_margin": 25, "competition": 3, '
    '"risk_tips": ["头部品牌集中"]}], '
    '"recommendation": {"top_pick": "开放式不入耳挂脖耳机", "verdict": "建议做", '
    '"score": 7.8, "reasons": ["搜索量高且增长快"], "risks": ["退货率偏高"], '
    '"entry_advice": "先小批量测款"}}'
)


def make_orchestrator() -> AgentOrchestrator:
    """构造最小编排器（两个工具方法只依赖 llm，不依赖 user/db）"""
    return AgentOrchestrator(user=None, db=None)


# ── 纯函数测试 ────────────────────────────────────────────────


def test_extract_json_strips_code_fence():
    """能剥离 ```json 围栏后解析出对象"""
    text = f"```json\n{VALID_JSON}\n```"
    parsed = _extract_json(text)
    assert parsed is not None
    assert parsed["market"]["monthly_search_volume"] == 126000


def test_extract_json_tolerates_trailing_text():
    """JSON 后带杂文也能提取"""
    text = VALID_JSON + "\n以上就是分析结果。"
    parsed = _extract_json(text)
    assert parsed is not None
    assert parsed["recommendation"]["score"] == 7.8


def test_extract_json_returns_none_on_garbage():
    """乱文本返回 None（fail-open 的前提）"""
    assert _extract_json("没有任何 JSON 的文本") is None
    assert _extract_json("") is None
    assert _extract_json(None) is None


def test_render_report_markdown_always_valid():
    """模板渲染出的 report 是合法 Markdown（含表格）"""
    parsed = _extract_json(VALID_JSON)
    md = _render_report_markdown(parsed, "蓝牙耳机", mode="select")
    assert md.startswith("## 「蓝牙耳机」市场分析")
    assert "| 月搜索量 | 126000 |" in md
    assert "候选商品" in md
    assert "| 开放式不入耳挂脖耳机 |" in md
    assert "**开放式不入耳挂脖耳机**" in md


def test_function_calling_tools_cover_full_listing_chain():
    """自然语言 Agent 必须能调用建商品和发布，而不只是分析工具。"""
    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "scrape_1688" in names
    assert "create_product" in names
    assert "generate_listing" in names
    assert "compliance_check" in names
    assert "push_to_shopify" in names


@pytest.mark.asyncio
async def test_run_react_reports_failed_tool_result(monkeypatch):
    """工具全部失败时，即使模型最后返回文本也不能标记 success。"""
    orch = make_orchestrator()
    responses = [
        {
            "content": "",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "calculate_profit", "arguments": "{}"},
            }],
        },
        {"content": "任务结束", "tool_calls": []},
    ]

    async def fake_chat(messages, tools=None, max_tokens=2000):
        return responses.pop(0)

    async def fake_execute(action, params):
        return {"action": action, "status": "failed", "error": "工具失败"}

    monkeypatch.setattr(orch.llm, "chat_with_tools", fake_chat)
    monkeypatch.setattr(orch, "_execute_step", fake_execute)

    result = await orch.run_react("算利润")

    assert result["status"] == "failed"
    assert result["steps"][0]["error"] == "工具失败"


@pytest.mark.asyncio
async def test_agent_generate_listing_persists_canonical_draft(
    db_session,
    monkeypatch,
):
    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "Premium wireless earbuds with long battery life."

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    user = User(email="agent-listing@test.com", username="agent-listing", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/agent-listing.html",
        title="Agent Listing 商品",
        price=19.9,
    )
    db_session.add(product)
    await db_session.flush()

    orch = AgentOrchestrator(user=user, db=db_session)
    result = await orch._do_generate_listing({
        "product_id": str(product.id),
        "platform": "amazon",
        "language": "en",
    })

    assert result["status"] == "success"
    assert result["data"]["listing_id"]
    assert result["data"]["compliance_status"] == "pass"
    listing = (
        await db_session.execute(
            select(ListingDraft).where(ListingDraft.id == UUID(result["data"]["listing_id"]))
        )
    ).scalar_one()
    assert listing.user_id == user.id
    assert listing.product_id == product.id
    assert listing.title == result["data"]["title"]


@pytest.mark.asyncio
async def test_agent_cannot_generate_from_other_users_product(db_session):
    owner = User(email="agent-owner@test.com", username="owner", password_hash="x")
    intruder = User(email="agent-intruder@test.com", username="intruder", password_hash="x")
    db_session.add_all([owner, intruder])
    await db_session.flush()
    product = Product(
        user_id=owner.id,
        url="https://detail.1688.com/offer/agent-owned.html",
        title="别人的商品",
    )
    db_session.add(product)
    await db_session.flush()

    orch = AgentOrchestrator(user=intruder, db=db_session)
    result = await orch._do_generate_listing({"product_id": str(product.id)})

    assert result["status"] == "failed"
    assert "商品不存在" in result["error"]


# ── 工具方法测试（monkeypatch DeepSeekService.generate） ──────


@pytest.mark.asyncio
async def test_select_products_structured_ok(monkeypatch):
    """合法 JSON → structured 有值、report 为模板 Markdown"""
    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return VALID_JSON
    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    result = await make_orchestrator()._do_select_products({"keyword": "蓝牙耳机"})

    assert result["status"] == "success"
    data = result["data"]
    assert data["keyword"] == "蓝牙耳机"
    assert data["structured"] is not None
    assert data["structured"]["market"]["monthly_search_volume"] == 126000
    assert len(data["structured"]["products"]) == 1
    assert data["report"].startswith("## 「蓝牙耳机」市场分析")


@pytest.mark.asyncio
async def test_select_products_fallback_on_bad_json(monkeypatch):
    """乱文本 → structured=None、report 为原始文本，不抛异常"""
    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "不好意思，这个品类数据暂时无法分析"
    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    result = await make_orchestrator()._do_select_products({"keyword": "蓝牙耳机"})

    assert result["status"] == "success"
    assert result["data"]["structured"] is None
    assert result["data"]["report"] == "不好意思，这个品类数据暂时无法分析"
    assert "降级" in result["summary"]


@pytest.mark.asyncio
async def test_analyze_category_structured_ok(monkeypatch):
    """品类分析同样产出 structured，且补上 data.keyword"""
    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return VALID_JSON
    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    result = await make_orchestrator()._do_analyze_category({"keyword": "蓝牙耳机"})

    assert result["status"] == "success"
    assert result["data"]["keyword"] == "蓝牙耳机"
    assert result["data"]["structured"] is not None
    assert result["data"]["report"].startswith("## 「蓝牙耳机」市场分析")


@pytest.mark.asyncio
async def test_analyze_category_fallback(monkeypatch):
    """品类分析乱文本 → 降级为原始文本，不抛异常"""
    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "【非 JSON】蓝牙耳机：搜索量大，竞争激烈……"
    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    result = await make_orchestrator()._do_analyze_category({"keyword": "蓝牙耳机"})

    assert result["status"] == "success"
    assert result["data"]["structured"] is None
    assert "【非 JSON】蓝牙耳机" in result["data"]["report"]
