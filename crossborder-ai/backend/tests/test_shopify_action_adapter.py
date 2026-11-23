"""Shopify 上架动作适配器测试。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services import shopify_action_adapter
from app.services.shopify_action_adapter import ShopifyPublishActionAdapter
from app.services.shopify_publish_service import ShopifyPublishResult
from app.services.workspaces import ensure_personal_workspace


async def _publish_context(db_session, email: str):
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
        url=f"https://example.com/{uuid4()}",
        title="Travel Mug",
        main_image_url="https://cdn.example.com/mug.webp",
    )
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="demo.myshopify.com",
        shop_domain="demo.myshopify.com",
        access_token="encrypted-token",
        is_active=True,
    )
    db_session.add_all([product, channel])
    await db_session.flush()
    listing = ListingDraft(
        user_id=user.id,
        product_id=product.id,
        platform="shopify",
        title="Insulated Travel Mug",
        description="Keeps drinks hot.",
        content_hash="hash-1",
    )
    variant = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="MUG-01",
        name="Black",
        price=29.9,
        stock_quantity=12,
        is_active=True,
    )
    db_session.add_all([listing, variant])
    await db_session.commit()
    return user, workspace, product, channel, listing, variant


@pytest.mark.asyncio
async def test_shopify_publish_adapter_preflights_executes_and_verifies(
    db_session,
    monkeypatch,
):
    user, _workspace, product, channel, listing, variant = await _publish_context(
        db_session,
        "shopify-action@example.com",
    )
    adapter = ShopifyPublishActionAdapter(db_session, user_id=user.id)
    input_data = {
        "product_id": str(product.id),
        "listing_id": str(listing.id),
        "channel_id": str(channel.id),
        "variant_ids": [str(variant.id)],
    }

    snapshot = await adapter.preflight(
        action_id="listings.publish",
        target_id=str(product.id),
        input_data=input_data,
    )

    assert snapshot["product_id"] == str(product.id)
    assert snapshot["variant_count"] == 1
    assert snapshot["image_count"] == 1
    assert snapshot["listing_version"] == 1

    publication = SimpleNamespace(
        id=uuid4(),
        external_product_id="gid://shopify/Product/123",
        external_url="https://demo.myshopify.com/admin/products/123",
        status="completed",
    )

    async def fake_publish(*args, **kwargs):
        return ShopifyPublishResult(
            publication=publication,
            prepared=SimpleNamespace(variant_count=1, image_count=1),
        )

    monkeypatch.setattr(
        shopify_action_adapter,
        "publish_shopify_product",
        fake_publish,
    )
    execution = await adapter.execute(
        action_id="listings.publish",
        target_id=str(product.id),
        input_data=input_data,
        idempotency_key="shopify-publish-action-1",
    )

    assert execution.external_id == "gid://shopify/Product/123"
    assert execution.output["publication_id"] == str(publication.id)

    async def fake_read(*_args, **_kwargs):
        return {
            "id": "gid://shopify/Product/123",
            "title": "Insulated Travel Mug",
            "status": "draft",
            "variants": [{"id": "gid://shopify/ProductVariant/1"}],
        }

    monkeypatch.setattr(adapter, "_read_remote_product", fake_read)
    verification = await adapter.verify(
        action_id="listings.publish",
        target_id=str(product.id),
        execution=execution,
    )

    assert verification.matched is True
    assert verification.snapshot["status"] == "draft"
    assert verification.details["variant_count"] == 1


@pytest.mark.asyncio
async def test_shopify_publish_adapter_rejects_foreign_product(db_session):
    owner, _workspace, _product, channel, listing, variant = await _publish_context(
        db_session,
        "shopify-action-owner@example.com",
    )
    other = User(
        email="shopify-action-other@example.com",
        username="shopify-action-other",
        password_hash="not-used",
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    adapter = ShopifyPublishActionAdapter(db_session, user_id=other.id)

    with pytest.raises(ValueError, match="商品"):
        await adapter.preflight(
            action_id="listings.publish",
            target_id=str(variant.product_id),
            input_data={
                "product_id": str(variant.product_id),
                "listing_id": str(listing.id),
                "channel_id": str(channel.id),
            },
        )
