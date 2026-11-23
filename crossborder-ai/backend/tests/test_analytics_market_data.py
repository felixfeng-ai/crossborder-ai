"""Web 品类分析入口必须复用真实市场服务，不得直接调用模型。"""

import pytest
from httpx import AsyncClient

from app.routers import analytics as analytics_module
from app.services.amazon_market_data import AmazonMarketDataNotConfigured


@pytest.mark.asyncio
async def test_web_category_endpoint_returns_structured_market_evidence(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch,
):
    class FakeMarketService:
        async def analyze_category(self, keyword: str):
            return {
                "keyword": keyword,
                "market": {
                    "sample_size": 120,
                    "data_completeness_pct": 91,
                },
                "segments": [{"label_zh": "无线易拆洗", "status": "有机会"}],
                "recommendation": {
                    "top_pick": "无线易拆洗",
                    "verdict": "有机会但需验证",
                },
                "data_quality": {
                    "provider": "jungle_scout",
                    "sample_size": 120,
                    "completeness_pct": 91,
                },
            }

    async def no_refresh(_db):
        return None

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(analytics_module.provider_config, "refresh", no_refresh)
    monkeypatch.setattr(
        analytics_module,
        "build_runtime_amazon_market_service",
        lambda: FakeMarketService(),
    )
    monkeypatch.setattr(
        analytics_module,
        "consume_feature_allowance",
        allowed,
    )

    response = await client.get(
        "/api/v1/analytics/category",
        params={"keyword": "宠物饮水机"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structured"]["segments"][0]["label_zh"] == "无线易拆洗"
    assert body["provider"] == "jungle_scout"
    assert "第三方估算" in body["report"]


@pytest.mark.asyncio
async def test_web_category_endpoint_rejects_unconfigured_market_data(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch,
):
    async def no_refresh(_db):
        return None

    def unconfigured():
        raise AmazonMarketDataNotConfigured("Amazon 市场数据源未配置")

    monkeypatch.setattr(analytics_module.provider_config, "refresh", no_refresh)
    monkeypatch.setattr(
        analytics_module,
        "build_runtime_amazon_market_service",
        unconfigured,
    )

    response = await client.get(
        "/api/v1/analytics/category",
        params={"keyword": "宠物饮水机"},
        headers=auth_headers,
    )

    assert response.status_code == 503
    assert "未配置" in response.json()["detail"]
