"""Shopify 远程改价与库存写回动作测试。"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.action_run import ActionRun
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.shopify_variant_adapter import ShopifyVariantActionAdapter
from app.services.action_dispatcher import resolve_action_adapter
from app.services.workspaces import ensure_personal_workspace


async def _variant_context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        url=f"https://example.com/{uuid4()}",
        title="旅行收纳包",
    )
    db_session.add(product)
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        sku="SKU-1",
        name="黑色",
        price=20.0,
        cost_price=9.0,
        stock_quantity=5,
    )
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="variant-store.myshopify.com",
        shop_domain="variant-store.myshopify.com",
        access_token=encrypt_value("shpat_variant"),
    )
    db_session.add_all([variant, channel])
    await db_session.flush()
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="shopify",
        title="旅行收纳包",
        content_hash="a" * 64,
        status="published",
    )
    db_session.add(listing)
    await db_session.flush()
    publication = Publication(
        user_id=user.id,
        listing_id=listing.id,
        platform="shopify",
        channel_id=str(channel.id),
        status="completed",
        external_product_id="gid://shopify/Product/500",
    )
    db_session.add(publication)
    await db_session.commit()
    return user, workspace, product, variant, channel


def _transport(state: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/products/500.json"):
            return httpx.Response(
                200,
                json={
                    "product": {
                        "id": 500,
                        "variants": [
                            {
                                "id": 900,
                                "sku": "SKU-1",
                                "price": state["price"],
                                "inventory_item_id": 700,
                                "inventory_management": "shopify",
                            }
                        ],
                    }
                },
            )
        if request.method == "GET" and path.endswith("/variants/900.json"):
            return httpx.Response(
                200,
                json={
                    "variant": {
                        "id": 900,
                        "sku": "SKU-1",
                        "price": state["price"],
                        "inventory_item_id": 700,
                    }
                },
            )
        if request.method == "PUT" and path.endswith("/variants/900.json"):
            body = json.loads(request.content)
            state["price"] = body["variant"]["price"]
            state["variant_puts"] += 1
            return httpx.Response(
                200,
                json={
                    "variant": {
                        "id": 900,
                        "sku": "SKU-1",
                        "price": state["price"],
                        "inventory_item_id": 700,
                    }
                },
            )
        if request.method == "GET" and path.endswith("/locations.json"):
            return httpx.Response(
                200,
                json={
                    "locations": [
                        {
                            "id": 300,
                            "name": "Primary",
                            "active": True,
                            "primary": True,
                        }
                    ]
                },
            )
        if request.method == "GET" and path.endswith("/inventory_levels.json"):
            return httpx.Response(
                200,
                json={
                    "inventory_levels": [
                        {
                            "inventory_item_id": 700,
                            "location_id": 300,
                            "available": state["stock"],
                        }
                    ]
                },
            )
        if request.method == "POST" and path.endswith("/inventory_levels/set.json"):
            body = json.loads(request.content)
            state["stock"] = int(body["available"])
            state["stock_sets"] += 1
            return httpx.Response(
                200,
                json={
                    "inventory_level": {
                        "inventory_item_id": 700,
                        "location_id": 300,
                        "available": state["stock"],
                    }
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_remote_price_update_preflights_executes_and_verifies(db_session):
    user, workspace, _product, variant, channel = await _variant_context(
        db_session,
        "variant-price@example.com",
    )
    state = {"price": "20.00", "stock": 5, "variant_puts": 0, "stock_sets": 0}
    adapter = ShopifyVariantActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "price": "24.99",
    }

    snapshot = await adapter.preflight(
        action_id="pricing.update",
        target_id=str(variant.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="pricing.update",
        target_id=str(variant.id),
        input_data=input_data,
        idempotency_key="pricing-1",
    )
    verification = await adapter.verify(
        action_id="pricing.update",
        target_id=str(variant.id),
        execution=execution,
    )

    assert snapshot["old_price"] == "20.00"
    assert snapshot["new_price"] == "24.99"
    assert state["price"] == "24.99"
    assert state["variant_puts"] == 1
    assert verification.matched is True
    assert verification.snapshot["price"] == "24.99"
    assert variant.price == 24.99


@pytest.mark.asyncio
async def test_remote_inventory_update_uses_primary_location_and_verifies(
    db_session,
):
    user, workspace, _product, variant, channel = await _variant_context(
        db_session,
        "variant-stock@example.com",
    )
    state = {"price": "20.00", "stock": 5, "variant_puts": 0, "stock_sets": 0}
    adapter = ShopifyVariantActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "stock_quantity": 12,
    }

    snapshot = await adapter.preflight(
        action_id="inventory.update",
        target_id=str(variant.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="inventory.update",
        target_id=str(variant.id),
        input_data=input_data,
        idempotency_key="stock-1",
    )
    verification = await adapter.verify(
        action_id="inventory.update",
        target_id=str(variant.id),
        execution=execution,
    )

    assert snapshot["old_stock"] == 5
    assert snapshot["new_stock"] == 12
    assert snapshot["location_id"] == "300"
    assert state["stock"] == 12
    assert state["stock_sets"] == 1
    assert verification.matched is True
    assert verification.snapshot["stock"] == 12
    assert variant.stock_quantity == 12


@pytest.mark.asyncio
async def test_remote_price_rejects_unpublished_variant(db_session):
    user, workspace, _product, variant, channel = await _variant_context(
        db_session,
        "variant-unpublished@example.com",
    )
    publication = (
        await db_session.execute(
            select(Publication).where(Publication.user_id == user.id)
        )
    ).scalar_one_or_none()
    assert publication is not None
    await db_session.delete(publication)
    await db_session.commit()
    adapter = ShopifyVariantActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(
            {"price": "20.00", "stock": 5, "variant_puts": 0, "stock_sets": 0}
        ),
    )

    with pytest.raises(ValueError, match="发布记录"):
        await adapter.preflight(
            action_id="pricing.update",
            target_id=str(variant.id),
            input_data={
                "channel_id": str(channel.id),
                "price": "24.99",
            },
        )


@pytest.mark.asyncio
async def test_dispatcher_routes_price_and_inventory_actions(db_session):
    user, workspace, _product, variant, _channel = await _variant_context(
        db_session,
        "variant-dispatcher@example.com",
    )
    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=uuid4(),
        action_id="pricing.update",
        platform="shopify",
        target_type="product_variant",
        target_id=str(variant.id),
        input_json="{}",
        status="queued",
        risk_level="high",
        autonomy_level="confirm",
        idempotency_key="variant-dispatcher-1",
    )

    adapter = await resolve_action_adapter(db_session, run)

    assert isinstance(adapter, ShopifyVariantActionAdapter)
