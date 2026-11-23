"""Agent 选品链路必须只使用真实 Provider 证据。"""

from datetime import datetime, timezone

import pytest

from app.models.user import User
from app.services.ai import agent_orchestrator as orchestrator_module
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services.amazon_market_data import (
    AmazonMarketDecisionService,
    AmazonProductSample,
    ProductDatabaseResult,
)


class StubMarketProvider:
    def __init__(self, *, with_units: bool = True):
        self.with_units = with_units
        self.calls = 0

    async def query_product_database(
        self,
        keyword: str,
        *,
        page_size: int = 100,
        max_pages: int = 2,
    ) -> ProductDatabaseResult:
        self.calls += 1
        items = [
            AmazonProductSample(
                asin=f"B000000{index:03d}",
                title=f"Pet fountain sample {index}",
                brand=f"Brand {index % 3}",
                price=25 + index,
                reviews=80 + index * 10,
                rating=4.5,
                monthly_units=500 + index * 30 if self.with_units else None,
                monthly_revenue=None,
                bsr=1000,
                sellers=2,
                listing_quality_score=80,
                referral_fee_rate=0.15,
                fulfillment_fee_usd=4.5,
                date_first_available=datetime(2026, 1, 1, tzinfo=timezone.utc),
                url=f"https://www.amazon.com/dp/B000000{index:03d}",
            )
            for index in range(12)
        ]
        return ProductDatabaseResult(
            items=items,
            total_results=120,
            observed_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
            pages_read=1,
        )

    async def historical_search_volume(
        self,
        keyword: str,
        *,
        days: int = 35,
    ) -> int:
        return 42000


@pytest.mark.asyncio
async def test_agent_category_uses_market_service_without_llm_numbers(
    db_session,
    monkeypatch,
):
    user = User(
        email="agent-market@test.com",
        username="agent-market",
        password_hash="x",
    )
    db_session.add(user)
    await db_session.flush()

    async def no_refresh(_db):
        return None

    async def forbid_llm(*_args, **_kwargs):
        raise AssertionError("选品分析不得让模型生成市场数字")

    market_service = AmazonMarketDecisionService(StubMarketProvider())
    monkeypatch.setattr(orchestrator_module.provider_config, "refresh", no_refresh)
    monkeypatch.setattr(
        orchestrator_module,
        "build_runtime_amazon_market_service",
        lambda **_kwargs: market_service,
    )
    monkeypatch.setattr(
        orchestrator_module.DeepSeekService,
        "generate",
        forbid_llm,
    )

    result = await AgentOrchestrator(user=user, db=db_session)._execute_step(
        "analyze_category",
        {"keyword": "宠物饮水机"},
    )

    assert result["status"] == "success"
    assert result["data"]["structured"]["segments"]
    assert result["data"]["structured"]["data_quality"]["provider"] == "jungle_scout"


@pytest.mark.asyncio
async def test_agent_missing_purchase_price_returns_needs_input(
    db_session,
    monkeypatch,
):
    user = User(
        email="agent-price-missing@test.com",
        username="agent-price-missing",
        password_hash="x",
    )
    db_session.add(user)
    await db_session.flush()

    async def no_refresh(_db):
        return None

    async def fake_scrape(*_args, **_kwargs):
        return {
            "title": "宠物饮水机无线静音款",
            "price": None,
            "sales_count": 100,
            "shop_name": "测试工厂",
        }

    def forbid_market(**_kwargs):
        raise AssertionError("采购价缺失时不得继续调用市场利润链路")

    monkeypatch.setattr(orchestrator_module.provider_config, "refresh", no_refresh)
    monkeypatch.setattr(orchestrator_module, "scrape_1688", fake_scrape)
    monkeypatch.setattr(
        orchestrator_module,
        "build_runtime_amazon_market_service",
        forbid_market,
    )

    result = await AgentOrchestrator(user=user, db=db_session)._execute_step(
        "analyze_product_decision",
        {"url": "https://detail.1688.com/offer/123.html"},
    )

    assert result["status"] == "needs_input"
    assert result["data"]["missing_fields"] == ["purchase_price_cny"]
    assert "采购价" in result["summary"]


@pytest.mark.asyncio
async def test_agent_product_decision_uses_real_market_and_profit_formula(
    db_session,
    monkeypatch,
):
    user = User(
        email="agent-product-profit@test.com",
        username="agent-product-profit",
        password_hash="x",
    )
    db_session.add(user)
    await db_session.flush()

    async def no_refresh(_db):
        return None

    async def fake_scrape(*_args, **_kwargs):
        return {
            "title": "宠物饮水机无线静音款",
            "price": 38,
            "sales_count": 100,
            "shop_name": "测试工厂",
        }

    market_service = AmazonMarketDecisionService(StubMarketProvider())
    monkeypatch.setattr(orchestrator_module.provider_config, "refresh", no_refresh)
    monkeypatch.setattr(orchestrator_module, "scrape_1688", fake_scrape)
    monkeypatch.setattr(
        orchestrator_module,
        "build_runtime_amazon_market_service",
        lambda **_kwargs: market_service,
    )

    result = await AgentOrchestrator(user=user, db=db_session)._execute_step(
        "analyze_product_decision",
        {
            "url": "https://detail.1688.com/offer/123.html",
            "shipping_cny": 20,
            "exchange_rate": 7.2,
        },
    )

    assert result["status"] == "success"
    assert result["data"]["decision_status"] in {
        "有机会",
        "有机会但需验证",
        "谨慎",
        "数据不足",
    }
    scenarios = result["data"]["profit_scenarios"]
    assert set(scenarios) == {"conservative", "base", "aggressive"}
    assert scenarios["base"]["formula_version"] == "profit-v1"
    assert scenarios["base"]["costs"]["product_cost_cny"] == 38
    assert scenarios["base"]["costs"]["shipping_cost_cny"] == 20
    assert result["data"]["exchange_rate_type"] == "user_input"


@pytest.mark.asyncio
async def test_agent_product_decision_requests_fee_inputs_when_missing(
    db_session,
    monkeypatch,
):
    user = User(
        email="agent-product-fee-input@test.com",
        username="agent-product-fee-input",
        password_hash="x",
    )
    db_session.add(user)
    await db_session.flush()

    async def no_refresh(_db):
        return None

    async def fake_scrape(*_args, **_kwargs):
        return {
            "title": "宠物饮水机无线静音款",
            "price": 38,
            "sales_count": 100,
            "shop_name": "测试工厂",
        }

    class NoFeeMarketService:
        async def analyze_product_link_facts(self, *, title, keyword=None):
            return {
                "market": {
                    "median_price_usd": 35.99,
                    "price_p25_usd": 29.99,
                    "price_p75_usd": 39.99,
                    "referral_fee_rate": None,
                    "fulfillment_fee_usd": None,
                },
                "recommendation": {"verdict": "有机会但需验证"},
            }

    monkeypatch.setattr(orchestrator_module.provider_config, "refresh", no_refresh)
    monkeypatch.setattr(orchestrator_module, "scrape_1688", fake_scrape)
    monkeypatch.setattr(
        orchestrator_module,
        "build_runtime_amazon_market_service",
        lambda **_kwargs: NoFeeMarketService(),
    )

    result = await AgentOrchestrator(user=user, db=db_session)._execute_step(
        "analyze_product_decision",
        {
            "url": "https://detail.1688.com/offer/123.html",
            "shipping_cny": 20,
            "exchange_rate": 7.2,
        },
    )

    assert result["status"] == "needs_input"
    assert set(result["data"]["missing_fields"]) == {
        "platform_fee_rate",
        "fulfillment_fee_usd",
    }


@pytest.mark.asyncio
async def test_agent_profit_tool_rejects_missing_cost(db_session):
    user = User(
        email="agent-profit-missing@test.com",
        username="agent-profit-missing",
        password_hash="x",
    )
    db_session.add(user)
    await db_session.flush()

    result = await AgentOrchestrator(
        user=user,
        db=db_session,
    )._execute_step(
        "calculate_profit",
        {
            "selling_price": 30,
            "exchange_rate": 7.2,
            "shipping_cost": 20,
            "platform_fee_rate": 0.15,
        },
    )

    assert result["status"] == "failed"
    assert "采购价" in result["error"]
