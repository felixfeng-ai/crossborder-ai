"""Temu API scope 到 Agent 能力矩阵的测试。"""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services.temu_capabilities import derive_temu_capabilities


def test_temu_capabilities_follow_granted_scopes():
    capabilities = derive_temu_capabilities(
        [
            "bg.local.goods.list.query",
            "bg.local.goods.stock.edit",
            "bg.local.goods.priceorder.change.sku.price",
        ],
        store_type="local",
    )

    assert capabilities["product.read"]["available"] is True
    assert capabilities["inventory.update"]["available"] is True
    assert capabilities["pricing.update"]["available"] is True
    assert capabilities["product.publish"]["available"] is False
    assert capabilities["order.read"]["available"] is False


def test_temu_order_scope_is_restricted_for_crossborder_store():
    capabilities = derive_temu_capabilities(
        ["bg.order.list.v2.get", "bg.order.detail.get"],
        store_type="crossborder",
    )

    assert capabilities["order.read"]["available"] is True
    assert capabilities["order.read"]["restriction_required"] is True
    assert "跨境" in capabilities["order.read"]["reason"]


def test_temu_local_scope_without_store_type_requires_confirmation():
    capabilities = derive_temu_capabilities(
        ["bg.local.goods.list.query"],
        store_type=None,
    )

    assert capabilities["product.read"]["available"] is True
    assert capabilities["product.read"]["restriction_required"] is True
    assert "店铺类型" in capabilities["product.read"]["reason"]


async def _register(client: AsyncClient, db_session, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@", 1)[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, user.id


@pytest.mark.asyncio
async def test_temu_scope_endpoint_never_returns_access_token(
    client: AsyncClient,
    db_session,
):
    headers, user_id = await _register(
        client,
        db_session,
        "temu-scope-endpoint@example.com",
    )
    token = "temu-secret-token-must-not-leak"
    connection = PlatformConnection(
        user_id=user_id,
        platform="temu",
        account_name="Temu US",
        external_account_id="1001",
        marketplace_id="us",
        credentials=encrypt_value(json.dumps({"access_token": token})),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "crossborder",
                "api_scope_list": [
                    "bg.local.goods.list.query",
                    "bg.order.list.v2.get",
                ],
            }
        ),
    )
    db_session.add(connection)
    await db_session.commit()

    response = await client.get(
        "/api/v1/platforms/temu/scopes",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert token not in response.text
    item = response.json()["connections"][0]
    assert item["external_account_id"] == "1001"
    assert item["capabilities"]["product.read"]["available"] is True
    assert item["capabilities"]["order.read"][
        "restriction_required"
    ] is True
