"""VeyaShip - 商品管理测试（F2 Refinery）

覆盖场景：
1. 手动录入商品（POST /api/v1/products/manual）
2. 获取商品列表（GET /api/v1/products）
3. 获取商品详情（GET /api/v1/products/{id}）
4. 1688 抓取（POST /api/v1/products/scrape）—— 无 API Key 时的降级行为
5. 未认证访问（401）
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_product_manual(client: AsyncClient, auth_headers: dict):
    """测试手动录入商品

    流程：先注册用户 → 获取 token → 手动录入 → 验证返回
    """
    product_data = {
        "url": "https://detail.1688.com/offer/123456.html",
        "title": "测试商品",
        "price": 29.99,
        "shop_name": "测试店铺",
    }
    response = await client.post(
        "/api/v1/products/manual",
        json=product_data,
        headers=auth_headers,
    )
    assert response.status_code == 201

    data = response.json()
    assert data["product"]["title"] == "测试商品"
    assert data["product"]["price"] == 29.99
    assert data["product"]["shop_name"] == "测试店铺"
    assert "id" in data["product"]


@pytest.mark.asyncio
async def test_create_own_product_without_external_url(
    client: AsyncClient,
    auth_headers: dict,
):
    response = await client.post(
        "/api/v1/products/manual",
        json={
            "title": "自有品牌保温杯",
            "description": "304 不锈钢，容量 500ml",
            "main_image_url": "https://cdn.example.com/own-cup.jpg",
            "price": 23.5,
            "origin_type": "own",
            "brand_name": "VeyaHome",
            "cost_currency": "CNY",
            "moq": 50,
            "lead_time_days": 7,
            "sku": "OWN-CUP-500",
            "stock_quantity": 120,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    product = response.json()["product"]
    assert product["title"] == "自有品牌保温杯"
    assert product["origin_type"] == "own"
    assert product["url"].startswith("own://")
    assert product["brand_name"] == "VeyaHome"
    assert product["cost_currency"] == "CNY"
    assert product["moq"] == 50
    assert product["lead_time_days"] == 7
    assert product["description"] == "304 不锈钢，容量 500ml"

    variants = await client.get(
        f"/api/v1/products/{product['id']}/variants",
        headers=auth_headers,
    )
    assert variants.status_code == 200
    assert variants.json()["items"][0]["sku"] == "OWN-CUP-500"
    assert variants.json()["items"][0]["stock_quantity"] == 120


@pytest.mark.asyncio
async def test_create_product_duplicate_url(client: AsyncClient, auth_headers: dict):
    """测试重复 URL 录入被拒绝"""
    # 第一次录入
    await client.post(
        "/api/v1/products/manual",
        json={"url": "https://detail.1688.com/offer/99999.html", "title": "第一次"},
        headers=auth_headers,
    )
    # 重复录入
    response = await client.post(
        "/api/v1/products/manual",
        json={"url": "https://detail.1688.com/offer/99999.html", "title": "第二次"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert "已存在" in response.json()["detail"] or "already" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_products(client: AsyncClient, auth_headers: dict):
    """测试商品列表分页"""
    # 创建 3 个商品
    for i in range(3):
        await client.post(
            "/api/v1/products/manual",
            json={
                "url": f"https://detail.1688.com/offer/{200000 + i}.html",
                "title": f"列表测试商品{i}",
            },
            headers=auth_headers,
        )

    # 查第一页，每页 20 条
    response = await client.get(
        "/api/v1/products",
        params={"page": 1, "page_size": 20},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_get_product_detail(client: AsyncClient, auth_headers: dict):
    """测试商品详情查询"""
    # 创建
    create_resp = await client.post(
        "/api/v1/products/manual",
        json={"url": "https://detail.1688.com/offer/55555.html", "title": "详情测试"},
        headers=auth_headers,
    )
    product_id = create_resp.json()["product"]["id"]

    # 查详情
    response = await client.get(f"/api/v1/products/{product_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "详情测试"
    assert data["url"] == "https://detail.1688.com/offer/55555.html"


@pytest.mark.asyncio
async def test_scrape_without_api_key(client: AsyncClient, auth_headers: dict):
    """测试无 API Key 时抓取 1688

    没有配置 Onebound API Key 时，应该给出清晰的错误提示。
    """
    response = await client.post(
        "/api/v1/products/scrape",
        json={"url": "https://detail.1688.com/offer/123456.html"},
        headers=auth_headers,
    )
    assert response.status_code in (400, 402, 502)


@pytest.mark.asyncio
async def test_products_unauthorized(client: AsyncClient):
    """测试未认证时返回 401"""
    response = await client.get("/api/v1/products")
    assert response.status_code == 401
