"""商品 SKU 变体 CRUD 与租户隔离测试。"""

import uuid

import pytest
from httpx import AsyncClient


async def _create_product(client: AsyncClient, headers: dict) -> str:
    response = await client.post(
        "/api/v1/products/manual",
        json={
            "url": f"https://detail.1688.com/offer/variant-{uuid.uuid4().hex}.html",
            "title": "变体测试商品",
            "price": 29.9,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["product"]["id"]


@pytest.mark.asyncio
async def test_create_list_update_delete_variants(
    client: AsyncClient,
    auth_headers: dict,
):
    product_id = await _create_product(client, auth_headers)
    created_ids: list[str] = []

    for color in ("白色", "黑色"):
        response = await client.post(
            f"/api/v1/products/{product_id}/variants",
            json={
                "sku": f"SKU-{color}-{uuid.uuid4().hex[:6]}",
                "attributes": {"颜色": color, "尺寸": "L"},
                "price": 39.9,
                "cost_price": 18.5,
                "stock_quantity": 100,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["id"])

    listed = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 2

    updated = await client.put(
        f"/api/v1/products/{product_id}/variants/{created_ids[0]}",
        json={"price": 45.0, "stock_quantity": 80},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["price"] == 45.0
    assert updated.json()["stock_quantity"] == 80

    deleted = await client.delete(
        f"/api/v1/products/{product_id}/variants/{created_ids[1]}",
        headers=auth_headers,
    )
    assert deleted.status_code == 200, deleted.text

    listed_again = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=auth_headers,
    )
    assert listed_again.json()["total"] == 1


@pytest.mark.asyncio
async def test_duplicate_sku_within_user_returns_409(
    client: AsyncClient,
    auth_headers: dict,
):
    product_id = await _create_product(client, auth_headers)
    sku = f"DUPLICATE-{uuid.uuid4().hex[:8]}"
    payload = {"sku": sku, "price": 19.9}

    first = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json=payload,
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "SKU" in second.json()["detail"]


@pytest.mark.asyncio
async def test_other_user_cannot_manage_variants(
    client: AsyncClient,
    auth_headers: dict,
):
    product_id = await _create_product(client, auth_headers)
    second = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"variant-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "variant-other",
            "password": "testpass123",
        },
    )
    assert second.status_code == 201, second.text
    other_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    create = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json={"sku": f"OTHER-{uuid.uuid4().hex[:6]}"},
        headers=other_headers,
    )
    assert create.status_code == 404

    listed = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=other_headers,
    )
    assert listed.status_code == 404


@pytest.mark.asyncio
async def test_batch_stock_update_is_atomic(
    client: AsyncClient,
    auth_headers: dict,
):
    """批量库存必须一次更新，且混入非法变体时整批回滚。"""
    product_id = await _create_product(client, auth_headers)
    variant_ids: list[str] = []
    for index in range(2):
        created = await client.post(
            f"/api/v1/products/{product_id}/variants",
            json={
                "sku": f"BATCH-{index}-{uuid.uuid4().hex[:6]}",
                "stock_quantity": 10,
            },
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        variant_ids.append(created.json()["id"])

    updated = await client.patch(
        f"/api/v1/products/{product_id}/variants/batch-stock",
        json={
            "items": [
                {"variant_id": variant_ids[0], "stock_quantity": 25},
                {"variant_id": variant_ids[1], "stock_quantity": 0},
            ]
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert {item["stock_quantity"] for item in updated.json()["items"]} == {25, 0}

    invalid = await client.patch(
        f"/api/v1/products/{product_id}/variants/batch-stock",
        json={
            "items": [
                {"variant_id": variant_ids[0], "stock_quantity": 99},
                {"variant_id": str(uuid.uuid4()), "stock_quantity": 88},
            ]
        },
        headers=auth_headers,
    )
    assert invalid.status_code == 404

    listed = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    stock_by_id = {
        item["id"]: item["stock_quantity"] for item in listed.json()["items"]
    }
    assert stock_by_id[variant_ids[0]] == 25


@pytest.mark.asyncio
async def test_batch_stock_rejects_duplicate_variant_ids(
    client: AsyncClient,
    auth_headers: dict,
):
    """重复变体 ID 会让批量语义不明确，必须在改库存前拒绝。"""
    product_id = await _create_product(client, auth_headers)
    created = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json={"sku": f"DUP-BATCH-{uuid.uuid4().hex[:6]}", "stock_quantity": 5},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    variant_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}/variants/batch-stock",
        json={
            "items": [
                {"variant_id": variant_id, "stock_quantity": 10},
                {"variant_id": variant_id, "stock_quantity": 20},
            ]
        },
        headers=auth_headers,
    )
    assert response.status_code == 422

    listed = await client.get(
        f"/api/v1/products/{product_id}/variants",
        headers=auth_headers,
    )
    assert listed.json()["items"][0]["stock_quantity"] == 5
