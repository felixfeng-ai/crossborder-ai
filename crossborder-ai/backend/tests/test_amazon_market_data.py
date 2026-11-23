"""Amazon US 市场数据 Provider 与决策聚合测试。"""

from datetime import datetime, timezone
from dataclasses import replace

import httpx
import pytest

from app.services.amazon_market_data import (
    AmazonMarketDataAuthorizationError,
    AmazonMarketDataNotConfigured,
    AmazonMarketDataRequestError,
    AmazonMarketDecisionService,
    AmazonProductSample,
    JungleScoutAmazonProvider,
    JustOneAmazonProvider,
    MarketQuery,
    ProductDatabaseResult,
    _normalize_product_node,
    _number,
    _parse_datetime,
    _review_pain_points,
    plan_queries_with_deepseek,
)


def _sample(
    asin: str,
    *,
    price: float = 29.99,
    units: int | None = 800,
    reviews: int = 320,
    fee_rate: float = 0.15,
    fulfillment_fee: float = 4.5,
) -> AmazonProductSample:
    return AmazonProductSample(
        asin=asin,
        title=f"Pet water fountain {asin}",
        brand=f"Brand {asin[-1]}",
        price=price,
        reviews=reviews,
        rating=4.5,
        monthly_units=units,
        monthly_revenue=price * units if units is not None else None,
        bsr=1200,
        sellers=3,
        listing_quality_score=82,
        referral_fee_rate=fee_rate,
        fulfillment_fee_usd=fulfillment_fee,
        date_first_available=None,
        url=f"https://www.amazon.com/dp/{asin}",
    )


class FakeProvider:
    """只返回结构化样本，便于验证决策层不补造数字。"""

    def __init__(self, products: list[AmazonProductSample], volume: int = 42000):
        self.products = products
        self.volume = volume
        self.queries: list[str] = []

    async def query_product_database(
        self,
        keyword: str,
        *,
        page_size: int = 100,
        max_pages: int = 2,
    ) -> ProductDatabaseResult:
        self.queries.append(keyword)
        return ProductDatabaseResult(
            items=self.products,
            total_results=len(self.products),
            observed_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
            pages_read=1,
        )

    async def historical_search_volume(
        self,
        keyword: str,
        *,
        days: int = 30,
    ) -> int | None:
        self.queries.append(f"volume:{keyword}")
        return self.volume


class PurchaseDisplayProvider(FakeProvider):
    """模拟 JustOneAPI：没有关键词搜索量，但有前台购买量展示。"""

    async def query_product_database(
        self,
        keyword: str,
        *,
        page_size: int = 100,
        max_pages: int = 1,
    ) -> ProductDatabaseResult:
        result = await super().query_product_database(
            keyword,
            page_size=page_size,
            max_pages=max_pages,
        )
        return ProductDatabaseResult(
            items=result.items,
            total_results=result.total_results,
            observed_at=result.observed_at,
            pages_read=result.pages_read,
            provider="justone_api",
        )

    async def historical_search_volume(
        self,
        keyword: str,
        *,
        days: int = 30,
    ) -> None:
        self.queries.append(f"volume:{keyword}")
        return None


class EnrichingDisplayProvider(PurchaseDisplayProvider):
    def __init__(self, products):
        super().__init__(products, volume=0)
        self.enriched = False

    async def enrich_products(
        self,
        products,
        *,
        detail_limit: int = 6,
        review_limit: int = 3,
    ):
        self.enriched = True
        first = replace(
            products[0],
            bsr=88,
            sellers=4,
            offer_count=4,
            source_provider="justone_api",
            review_titles=["Filter gets dirty quickly"],
        )
        return [first, *products[1:]]


@pytest.mark.asyncio
async def test_jungle_scout_uses_required_auth_marketplace_and_pagination():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "KEY_NAME:API_KEY"
        assert request.headers["X-API-Type"] == "junglescout"
        assert request.url.params["marketplace"] == "us"
        if request.url.path.endswith("/product_database_query"):
            payload = __import__("json").loads(request.content)
            assert payload["data"]["attributes"]["include_keywords"] == [
                "pet water fountain"
            ]
            page_number = int(request.url.params.get("page[number]", "1"))
            item_id = "B000000001" if page_number == 1 else "B000000002"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": item_id,
                            "type": "product_database_query",
                            "attributes": {
                                "title": f"Fountain {item_id}",
                                "brand": "Aqua",
                                "price": 29.99,
                                "reviews": 120,
                                "rating": 4.6,
                                "approximate_30_day_units_sold": 700,
                                "available": True,
                            },
                        }
                    ],
                    "meta": {"page": {"total_results": 2}},
                    "links": {
                        "next": (
                            "https://developer.junglescout.com/api/"
                            "product_database_query?marketplace=us&page[size]=1"
                            "&page[number]=2"
                        )
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/historical_search_volume"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "attributes": {
                                "estimated_exact_search_volume": 10000,
                            }
                        },
                        {
                            "attributes": {
                                "estimated_exact_search_volume": 12000,
                            }
                        },
                    ]
                },
                request=request,
            )
        raise AssertionError(f"unexpected path: {request.url}")

    provider = JungleScoutAmazonProvider(
        key_name="KEY_NAME",
        api_key="API_KEY",
        marketplace="us",
        transport=httpx.MockTransport(handler),
    )

    products = await provider.query_product_database(
        "pet water fountain",
        page_size=1,
        max_pages=2,
    )
    volume = await provider.historical_search_volume(
        "pet water fountain",
        days=14,
    )

    assert [item.asin for item in products.items] == [
        "B000000001",
        "B000000002",
    ]
    assert products.pages_read == 2
    assert volume == 22000
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_jungle_scout_missing_credentials_fails_without_request():
    provider = JungleScoutAmazonProvider(
        key_name="",
        api_key="",
        marketplace="us",
    )

    with pytest.raises(AmazonMarketDataNotConfigured, match="未配置"):
        await provider.query_product_database("pet water fountain")


@pytest.mark.asyncio
async def test_justone_amazon_search_and_detail_use_observed_product_facts():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["token"] == "TOKEN"
        assert request.url.params["country"] == "US"
        if request.url.path.endswith("/search-products/v1"):
            assert request.url.params["keyword"] == "wireless pet water fountain"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "total_products": 240,
                        "country": "US",
                        "domain": "amazon.com",
                        "products": [
                            {
                                "asin": "B000JUST01",
                                "product_title": "Wireless Pet Water Fountain",
                                "product_url": (
                                    "https://www.amazon.com/dp/B000JUST01"
                                ),
                                "product_price": "$39.99",
                                "product_price_value": 39.99,
                                "product_num_ratings": 1200,
                                "product_star_rating": "4.6",
                                "product_num_offers": 4,
                                "sales_volume": "2K+ bought in past month",
                                "product_byline": "Brand: Aqua Pet",
                                "is_best_seller": True,
                                "product_availability": "In Stock",
                            }
                        ],
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/get-product-detail/v1"):
            assert request.url.params["asin"] == "B000JUST01"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "asin": "B000JUST01",
                        "product_title": "Wireless Pet Water Fountain",
                        "product_price_value": 38.99,
                        "product_num_ratings": 1210,
                        "product_star_rating": "4.6",
                        "sales_volume": "2K+ bought in past month",
                        "best_sellers_rank": [
                            {"rank": 153, "category": "Pet Supplies"}
                        ],
                        "product_num_offers": 5,
                        "product_availability": "In Stock",
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/get-product-top-reviews/v1"):
            assert request.url.params["asin"] == "B000JUST01"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "top_reviews": [
                            {
                                "review_title": "Pump stopped working",
                                "review_comment": "The pump is noisy and hard to clean.",
                                "review_star_rating": "2",
                            }
                        ]
                    },
                },
                request=request,
            )
        raise AssertionError(f"unexpected path: {request.url}")

    provider = JustOneAmazonProvider(
        token="TOKEN",
        transport=httpx.MockTransport(handler),
    )
    page = await provider.query_product_database(
        "wireless pet water fountain",
        max_pages=1,
    )
    enriched = await provider.enrich_products(
        page.items,
        detail_limit=1,
        review_limit=1,
    )

    assert page.provider == "justone_api"
    assert page.total_results == 240
    assert page.items[0].purchase_volume_min == 2000
    assert page.items[0].purchase_volume_raw == "2K+ bought in past month"
    assert page.items[0].is_best_seller is True
    assert enriched[0].bsr == 153
    assert enriched[0].sellers == 5
    assert enriched[0].review_titles == ["Pump stopped working"]
    assert len(requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("business_code", "error_type", "message"),
    [
        (600, AmazonMarketDataAuthorizationError, "权限"),
        (601, AmazonMarketDataRequestError, "余额"),
        (602, AmazonMarketDataRequestError, "预算"),
        (302, AmazonMarketDataRequestError, "频繁"),
    ],
)
async def test_justone_business_errors_are_actionable(
    business_code,
    error_type,
    message,
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": business_code, "message": "provider error"},
            request=request,
        )

    provider = JustOneAmazonProvider(
        token="TOKEN",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(error_type, match=message):
        await provider.query_product_database("pet water fountain")


@pytest.mark.asyncio
async def test_category_decision_splits_pet_fountain_and_marks_third_party_data():
    products = [
        _sample(f"B0000000{index:02d}", price=24.99 + index, units=500 + index * 20)
        for index in range(1, 13)
    ]
    provider = FakeProvider(products)
    service = AmazonMarketDecisionService(provider)

    result = await service.analyze_category("宠物饮水机")

    assert len(result["segments"]) == 5
    assert result["market"]["marketplace"] == "us"
    assert result["market"]["currency"] == "USD"
    assert result["market"]["sample_size"] >= 10
    assert result["data_quality"]["provider"] == "jungle_scout"
    assert result["data_quality"]["completeness_pct"] > 0
    assert result["recommendation"]["verdict"] in {
        "有机会",
        "有机会但需验证",
        "谨慎",
        "数据不足",
    }
    assert "wireless pet water fountain" in provider.queries
    assert "stainless steel large capacity pet water fountain" in provider.queries
    assert result["evidence"]
    assert all(
        item["type"] == "third_party_estimate"
        for item in result["evidence"]
        if item["metric"] in {"monthly_search_volume", "monthly_units"}
    )


@pytest.mark.asyncio
async def test_category_decision_never_substitutes_missing_units_with_zero():
    products = [
        _sample(f"B0000001{index:02d}", units=None)
        for index in range(1, 13)
    ]
    service = AmazonMarketDecisionService(FakeProvider(products))

    result = await service.analyze_category("宠物饮水机")

    assert result["recommendation"]["verdict"] == "数据不足"
    assert "monthly_units" in result["data_quality"]["missing_fields"]
    assert all(
        segment["metrics"].get("monthly_units") is None
        for segment in result["segments"]
    )


@pytest.mark.asyncio
async def test_category_decision_uses_purchase_display_without_fake_search_volume():
    products = [
        _sample(
            f"B0000003{index:02d}",
            price=29.99 + index,
            units=None,
        )
        for index in range(1, 13)
    ]
    products = [
        replace(
            item,
            purchase_volume_min=1000 + index * 100,
            purchase_volume_raw="1K+ bought in past month",
            purchase_volume_period="past_month",
            purchase_volume_is_lower_bound=True,
            source_provider="justone_api",
        )
        for index, item in enumerate(products)
    ]
    service = AmazonMarketDecisionService(
        PurchaseDisplayProvider(products, volume=0)
    )

    result = await service.analyze_category("宠物饮水机")

    assert result["recommendation"]["verdict"] != "数据不足"
    assert result["market"]["monthly_search_volume"] is None
    assert result["market"]["purchase_volume_coverage_pct"] > 0
    assert result["market"]["median_purchase_volume_min"] >= 1000
    assert any(
        item["type"] == "observed_display_range"
        for item in result["evidence"]
    )


@pytest.mark.asyncio
async def test_category_decision_enriches_global_top_product_once():
    products = [
        replace(
            _sample(f"B0000004{index:02d}", units=None),
            purchase_volume_min=1000 + index,
            purchase_volume_raw="1K+ bought in past month",
            source_provider="justone_api",
        )
        for index in range(12)
    ]
    provider = EnrichingDisplayProvider(products)

    result = await AmazonMarketDecisionService(provider).analyze_category(
        "宠物饮水机"
    )

    assert provider.enriched is True
    assert result["segments"][0]["sample_products"][0]["bsr"] == 88
    assert result["data_quality"]["provider"] == "justone_api"


def test_known_blueprint_returns_explicit_english_queries():
    plan = AmazonMarketDecisionService.resolve_known_blueprint("宠物饮水机")

    assert plan is not None
    assert isinstance(plan.base, MarketQuery)
    assert len(plan.segments) == 5
    assert all(item.keyword.isascii() for item in plan.segments)


def test_normalizer_handles_nested_fee_and_date_formats():
    node = {
        "id": "B000000099",
        "attributes": {
            "title": "Nested fountain",
            "price": "$29.99",
            "reviews": "320",
            "approximate_30_day_units_sold": 450,
            "date_first_available": "2025-01-02",
            "fee_breakdown": {
                "referral_fee": {"amount": 4.5},
                "fba_fee": 5.25,
            },
        },
    }

    sample = _normalize_product_node(node)

    assert sample is not None
    assert sample.price == 29.99
    assert round(sample.referral_fee_rate, 2) == 0.15
    assert sample.fulfillment_fee_usd == 5.25
    assert sample.date_first_available is not None
    assert _number("12%") == 0.12
    assert _number({"value": "1,200"}) == 1200
    assert _parse_datetime("2026-01-01T00:00:00Z") is not None
    assert _normalize_product_node({"id": "missing-title"}) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type", "message"),
    [
        (401, AmazonMarketDataAuthorizationError, "鉴权"),
        (429, AmazonMarketDataRequestError, "频繁"),
        (500, AmazonMarketDataRequestError, "请求失败"),
    ],
)
async def test_jungle_scout_maps_provider_errors(
    status_code,
    error_type,
    message,
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    provider = JungleScoutAmazonProvider(
        key_name="key",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(error_type, match=message):
        await provider.query_product_database("pet water fountain")


@pytest.mark.asyncio
async def test_jungle_scout_rejects_non_us_marketplace():
    provider = JungleScoutAmazonProvider(
        key_name="key",
        api_key="secret",
        marketplace="uk",
    )

    with pytest.raises(AmazonMarketDataNotConfigured, match="Amazon US"):
        await provider.query_product_database("pet water fountain")


@pytest.mark.asyncio
async def test_query_planner_rejects_numbers_and_keeps_valid_english_terms(monkeypatch):
    from app.services.ai.deepseek import DeepSeekService

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return (
            '{"concept":"饮水机","queries":['
            '{"key":"a","label_zh":"无线","keyword":"wireless pet fountain"},'
            '{"key":"b","label_zh":"重复","keyword":"wireless pet fountain"},'
            '{"key":"c","label_zh":"非法","keyword":"无线饮水机"},'
            '{"key":"d","label_zh":"不锈钢","keyword":"stainless steel pet fountain"}]}'
        )

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    queries = await plan_queries_with_deepseek("宠物饮水机")

    assert [item.keyword for item in queries] == [
        "wireless pet fountain",
        "stainless steel pet fountain",
    ]


@pytest.mark.asyncio
async def test_custom_queries_use_planner_only_for_chinese():
    calls: list[str] = []

    async def planner(keyword: str, context: str | None):
        calls.append(keyword)
        return [MarketQuery("custom", "自定义", "custom pet fountain")]

    service = AmazonMarketDecisionService(
        FakeProvider([_sample(f"B0000002{index:02d}") for index in range(1, 13)]),
        query_planner=planner,
    )
    result = await service.analyze("智能宠物水吧")

    assert calls == ["智能宠物水吧"]
    assert result["segments"][0]["keyword"] == "custom pet fountain"


def test_score_and_risks_cover_blocking_thresholds():
    assert AmazonMarketDecisionService._score(
        {
            "monthly_units": 1500,
            "median_reviews": 20,
            "head_concentration": 30,
            "new_product_share_pct": 40,
        }
    ) == 10
    assert AmazonMarketDecisionService._decision_status(
        {
            "data_completeness_pct": 90,
            "sample_size": 20,
            "monthly_units": 300,
            "avg_price_usd": 29.99,
        },
        4,
    ) == "谨慎"
    risks = AmazonMarketDecisionService._risk_flags(
        MarketQuery("x", "测试", "water fountain"),
        {
            "median_reviews": 1000,
            "head_concentration": 80,
            "price_war_level": 5,
        },
    )
    assert "头部品牌集中" in risks
    assert "低价竞争明显" in AmazonMarketDecisionService._risk_flags(
        MarketQuery("x", "测试", "generic product"),
        {"price_war_level": 5},
    )
    pains = _review_pain_points(
        [
            replace(
                _sample("B000000999"),
                review_titles=["Pump stopped working and noisy"],
                review_comments=["The filter is hard to clean and it started leaking."],
            )
        ]
    )
    assert {"泵体故障", "噪音", "滤芯耗材", "清洗困难", "漏水"} <= set(pains)


def test_runtime_market_provider_prefers_justone_token(monkeypatch):
    from app.services import provider_config

    values = {
        ("justone", "token"): "justone-token",
        ("deepseek", "api_key"): "",
        ("jungle_scout", "key_name"): "unused",
        ("jungle_scout", "api_key"): "unused",
        ("jungle_scout", "marketplace"): "us",
    }
    monkeypatch.setattr(
        provider_config,
        "get",
        lambda provider, field, default="": values.get(
            (provider, field),
            default,
        ),
    )

    service = __import__(
        "app.services.amazon_market_data",
        fromlist=["build_runtime_amazon_market_service"],
    ).build_runtime_amazon_market_service()

    assert isinstance(service.provider, JustOneAmazonProvider)
