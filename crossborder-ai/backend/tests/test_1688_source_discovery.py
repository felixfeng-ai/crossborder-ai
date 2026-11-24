"""1688 货源发现服务测试。"""

import httpx
import pytest

from app.services.source_discovery import (
    SourceDiscoveryError,
    SourceDiscoveryInputError,
    search_1688_sources,
)


def _justone_item() -> dict:
    return {
        "item_id": 628196518518,
        "title": "跨境无线宠物饮水机静音大容量",
        "product_url": "https://detail.1688.com/offer/628196518518.html",
        "img": "https://cbu01.alicdn.com/img/pet-fountain.jpg",
        "price": "18.50-25.00",
        "price_info": {"sale_price": "18.50"},
        "moq": 2,
        "quantity_begin": 2,
        "quantity_prices": [
            {"begin_num": 2, "end_num": 99, "price": "25.00"},
            {"begin_num": 100, "end_num": None, "price": "18.50"},
        ],
        "sale_info": {
            "sale_quantity": "1.2万",
            "sale_quantity_int": 12000,
            "orders_count": 860,
        },
        "delivery_info": {"area_from": ["浙江", "义乌"]},
        "shop_info": {
            "company_name": "义乌市示例宠物用品厂",
            "shop_url": "https://example.1688.com",
            "shop_years": 6,
            "biz_type": "生产加工",
            "location": ["浙江", "金华"],
            "service_tags": ["48小时发货", "支持一件代发"],
            "is_factory": True,
            "is_super_factory": True,
            "factory_inspection": True,
            "score_info": {"composite_new_score": "4.8"},
        },
        "tags": ["跨境专供", "源头工厂"],
    }


def _justone_response(*, items: list[dict] | None = None) -> dict:
    return {
        "code": 0,
        "message": "",
        "data": {
            "keyword": "宠物饮水机",
            "page": 1,
            "page_size": 10,
            "total_count": 1,
            "items": items if items is not None else [_justone_item()],
        },
    }


@pytest.mark.asyncio
async def test_justone_keyword_search_normalizes_supplier_fields():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["token"] = request.url.params.get("token")
        captured["keyword"] = request.url.params.get("keyword")
        captured["page_size"] = request.url.params.get("pageSize")
        captured["sort"] = request.url.params.get("sort")
        return httpx.Response(200, json=_justone_response())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            justone_token="justone-token",
            client=client,
        )

    assert captured == {
        "path": "/api/1688/search-item-list/v2",
        "token": "justone-token",
        "keyword": "宠物饮水机",
        "page_size": "10",
        "sort": "sales",
    }
    assert result["provider"] == "justone"
    assert result["search_mode"] == "text"
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["item_id"] == "628196518518"
    assert item["url"].endswith("/628196518518.html")
    assert item["price"] == "18.50-25.00"
    assert item["price_min_cny"] == 18.5
    assert item["moq"] == 2
    assert item["sale_quantity"] == 12000
    assert item["shop_name"] == "义乌市示例宠物用品厂"
    assert item["shop_years"] == 6
    assert item["is_factory"] is True
    assert item["factory_inspection"] is True
    assert item["location"] == "浙江 义乌"
    assert "支持一件代发" in item["service_tags"]
    assert "justone-token" not in str(result)


@pytest.mark.asyncio
async def test_image_search_runs_before_keyword_search():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/search-item-by-image/v1"):
            assert request.url.params["imgUrl"] == "https://img.example.com/a.jpg"
            return httpx.Response(200, json=_justone_response())
        raise AssertionError(f"unexpected path: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            image_url="https://img.example.com/a.jpg",
            justone_token="justone-token",
            client=client,
        )

    assert paths == ["/api/1688/search-item-by-image/v1"]
    assert result["search_mode"] == "image"
    assert result["image_search_used"] is True
    assert result["limitations"][0].startswith("图片搜索返回相似货源")


@pytest.mark.asyncio
async def test_image_search_failure_falls_back_to_keyword():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/search-item-by-image/v1"):
            return httpx.Response(500, json={"code": 500})
        if request.url.path.endswith("/search-item-list/v2"):
            return httpx.Response(200, json=_justone_response())
        raise AssertionError(f"unexpected path: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            image_url="https://img.example.com/a.jpg",
            justone_token="justone-token",
            client=client,
        )

    assert paths == [
        "/api/1688/search-item-by-image/v1",
        "/api/1688/search-item-list/v2",
    ]
    assert result["search_mode"] == "text"
    assert result["image_search_used"] is False
    assert result["image_fallback_reason"]


@pytest.mark.asyncio
async def test_empty_image_result_falls_back_to_keyword():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/search-item-by-image/v1"):
            return httpx.Response(
                200,
                json=_justone_response(items=[]),
            )
        if request.url.path.endswith("/search-item-list/v2"):
            return httpx.Response(200, json=_justone_response())
        raise AssertionError(f"unexpected path: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            image_url="https://img.example.com/a.jpg",
            justone_token="justone-token",
            client=client,
        )

    assert paths == [
        "/api/1688/search-item-by-image/v1",
        "/api/1688/search-item-list/v2",
    ]
    assert result["search_mode"] == "text"
    assert result["image_fallback_reason"] == (
        "图片搜索未返回货源，已改用关键词搜索"
    )


@pytest.mark.asyncio
async def test_justone_failure_falls_back_to_onebound():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/search-item-list/v2"):
            return httpx.Response(200, json={"code": 601, "message": "no balance"})
        if request.url.path.endswith("/1688/item_search"):
            assert request.url.params["key"] == "onebound-key"
            assert request.url.params["secret"] == "onebound-secret"
            assert request.url.params["q"] == "宠物饮水机"
            return httpx.Response(
                200,
                json={
                    "items": {
                        "item": [
                            {
                                "num_iid": "99887766",
                                "title": "宠物饮水机一件代发",
                                "pic_url": "https://img.example.com/onebound.jpg",
                                "detail_url": (
                                    "https://detail.1688.com/offer/99887766.html"
                                ),
                                "price": "16.80",
                                "min_num": 3,
                                "sales": 3200,
                                "seller_nick": "深圳示例工厂",
                                "location": "广东 深圳",
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected path: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            justone_token="justone-token",
            onebound_api_key="onebound-key",
            onebound_api_secret="onebound-secret",
            client=client,
        )

    assert paths == [
        "/api/1688/search-item-list/v2",
        "/1688/item_search",
    ]
    assert result["provider"] == "onebound"
    assert result["provider_fallback_reason"]
    assert result["items"][0]["item_id"] == "99887766"
    assert result["items"][0]["price_min_cny"] == 16.8


@pytest.mark.asyncio
async def test_search_requires_keyword_and_configured_provider():
    with pytest.raises(SourceDiscoveryInputError, match="关键词"):
        await search_1688_sources(" ", justone_token="token")

    with pytest.raises(SourceDiscoveryError, match="尚未配置"):
        await search_1688_sources("宠物饮水机")

    with pytest.raises(SourceDiscoveryInputError, match="图片地址"):
        await search_1688_sources(
            "宠物饮水机",
            image_url="javascript:alert(1)",
            justone_token="token",
        )


@pytest.mark.asyncio
async def test_malformed_justone_response_returns_safe_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(SourceDiscoveryError, match="暂时不可用") as error:
            await search_1688_sources(
                "宠物饮水机",
                justone_token="justone-secret",
                client=client,
            )

    assert "justone-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_justone_chinese_sales_text_is_normalized():
    """接口只返回“1.2万”这类中文文本时，也要保留可比较的销量。"""

    item = _justone_item()
    item["sale_info"] = {"sale_quantity": "1.2万", "orders_count": 860}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_justone_response(items=[item]))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            justone_token="justone-token",
            client=client,
        )

    assert result["items"][0]["sale_quantity"] == 12000


@pytest.mark.asyncio
async def test_supplier_links_reject_non_http_schemes():
    """供应商响应属于外部数据，不能把脚本协议直接透传给用户界面。"""

    item = _justone_item()
    item["product_url"] = "javascript:alert(1)"
    item["img"] = "data:image/svg+xml,<svg onload=alert(1)>"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_justone_response(items=[item]))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await search_1688_sources(
            "宠物饮水机",
            justone_token="justone-token",
            client=client,
        )

    normalized = result["items"][0]
    assert normalized["url"] == (
        "https://detail.1688.com/offer/628196518518.html"
    )
    assert normalized["image_url"] is None
