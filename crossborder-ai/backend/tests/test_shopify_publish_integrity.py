"""Shopify 发布完整性与价格语义测试。"""

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services.ai.deepseek import DeepSeekService
from app.services.listing_service import persist_generated_listing
from app.services.shopify_publish_service import (
    PreparedShopifyProduct,
    ShopifyPublishResult,
    ShopifyPublishValidationError,
    _load_active_variants,
    build_shopify_product_payload,
    publish_shopify_product,
)
import app.routers.shopify as shopify_module


def _variant(
    *,
    product_id,
    user_id,
    sku: str,
    price: float | None,
    attributes: dict | None = None,
    image_url: str | None = None,
) -> ProductVariant:
    return ProductVariant(
        id=uuid.uuid4(),
        user_id=user_id,
        product_id=product_id,
        sku=sku,
        name=" / ".join((attributes or {}).values()) or None,
        attributes_json=json.dumps(attributes or {}, ensure_ascii=False),
        price=price,
        cost_price=12.5,
        stock_quantity=18,
        barcode="690000000001",
        image_url=image_url,
        is_active=True,
    )


def test_build_payload_uses_variant_sale_price_and_complete_content():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = Product(
        id=product_id,
        user_id=user_id,
        url="https://detail.1688.com/offer/integrity.html",
        title="采购商品标题",
        description="供货商品描述",
        price=12.5,
        shop_name="义乌供应链",
        main_image_url="https://cdn.example.com/main.jpg",
    )
    listing = ListingDraft(
        id=uuid.uuid4(),
        user_id=user_id,
        product_id=product_id,
        platform="shopify",
        language="en",
        tone="professional",
        status="ready",
        title="Premium Storage Box",
        description="<p>Durable storage for small homes.</p>",
        bullet_points=json.dumps(
            ["Reinforced handles", "Folds flat"],
            ensure_ascii=False,
        ),
        seo_title="Premium Storage Box | VeyaShip",
        seo_description="Shop a durable foldable storage box.",
        version=1,
        content_hash="x" * 64,
        compliance_status="pass",
        compliance_violations="[]",
    )
    variants = [
        _variant(
            product_id=product_id,
            user_id=user_id,
            sku="BOX-BLACK-M",
            price=39.9,
            attributes={"Color": "Black", "Size": "M"},
            image_url="/api/v1/images/assets/black-m/file",
        ),
        _variant(
            product_id=product_id,
            user_id=user_id,
            sku="BOX-WHITE-L",
            price=42.9,
            attributes={"Color": "White", "Size": "L"},
        ),
    ]

    prepared = build_shopify_product_payload(
        product,
        listing,
        variants,
        app_url="https://veyaship.com",
    )
    payload = prepared.product

    assert payload["title"] == "Premium Storage Box"
    assert "Durable storage" in payload["body_html"]
    assert "Reinforced handles" in payload["body_html"]
    assert payload["variants"][0]["price"] == "39.90"
    assert payload["variants"][0]["sku"] == "BOX-BLACK-M"
    assert payload["variants"][0]["inventory_quantity"] == 18
    assert payload["variants"][0]["option1"] == "Black"
    assert payload["variants"][0]["option2"] == "M"
    assert all(item["price"] != "12.50" for item in payload["variants"])
    assert payload["images"] == [
        {"src": "https://cdn.example.com/main.jpg", "alt": "Premium Storage Box"},
        {
            "src": "https://veyaship.com/api/v1/images/assets/black-m/file",
            "alt": "BOX-BLACK-M",
        },
    ]
    assert payload["metafields"] == [
        {
            "namespace": "global",
            "key": "title_tag",
            "value": "Premium Storage Box | VeyaShip",
            "type": "single_line_text_field",
        },
        {
            "namespace": "global",
            "key": "description_tag",
            "value": "Shop a durable foldable storage box.",
            "type": "single_line_text_field",
        },
    ]
    assert prepared.variant_count == 2
    assert prepared.image_count == 2


def test_build_payload_flattens_multiline_seo_metafields():
    """Shopify 单行 SEO 元字段不能包含换行。"""

    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = Product(
        id=product_id,
        user_id=user_id,
        url="https://detail.1688.com/offer/seo-lines.html",
        title="SEO 商品",
    )
    listing = ListingDraft(
        id=uuid.uuid4(),
        user_id=user_id,
        product_id=product_id,
        platform="shopify",
        language="en",
        tone="professional",
        status="ready",
        title="SEO Product",
        description="<p>Product description.</p>",
        bullet_points="[]",
        seo_title="SEO Product\n| VeyaShip",
        seo_description="Line one.\nLine two.\r\nLine three.",
        version=1,
        content_hash="s" * 64,
        compliance_status="pass",
        compliance_violations="[]",
    )
    variant = _variant(
        product_id=product_id,
        user_id=user_id,
        sku="SEO-001",
        price=29.9,
    )

    payload = build_shopify_product_payload(
        product,
        listing,
        [variant],
        app_url="https://veyaship.com",
    ).product
    metafields = {item["key"]: item["value"] for item in payload["metafields"]}

    assert metafields["title_tag"] == "SEO Product | VeyaShip"
    assert metafields["description_tag"] == "Line one. Line two. Line three."
    assert all("\n" not in value and "\r" not in value for value in metafields.values())


def test_build_payload_rejects_missing_variants_or_sale_price():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = Product(
        id=product_id,
        user_id=user_id,
        url="https://detail.1688.com/offer/integrity-empty.html",
        title="商品",
        price=12.5,
    )
    listing = ListingDraft(
        id=uuid.uuid4(),
        user_id=user_id,
        product_id=product_id,
        platform="shopify",
        language="en",
        tone="professional",
        status="ready",
        title="Listing",
        description="Description",
        bullet_points="[]",
        seo_title="",
        seo_description="",
        version=1,
        content_hash="x" * 64,
        compliance_status="pass",
        compliance_violations="[]",
    )

    with pytest.raises(ShopifyPublishValidationError, match="启用 SKU"):
        build_shopify_product_payload(product, listing, [], app_url="https://veyaship.com")

    missing_price = _variant(
        product_id=product_id,
        user_id=user_id,
        sku="NO-PRICE",
        price=None,
        attributes={"Color": "Black"},
    )
    with pytest.raises(ShopifyPublishValidationError, match="NO-PRICE"):
        build_shopify_product_payload(
            product,
            listing,
            [missing_price],
            app_url="https://veyaship.com",
        )


def test_build_payload_rejects_more_than_three_options():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = Product(
        id=product_id,
        user_id=user_id,
        url="https://detail.1688.com/offer/integrity-options.html",
        title="商品",
        price=12.5,
    )
    listing = ListingDraft(
        id=uuid.uuid4(),
        user_id=user_id,
        product_id=product_id,
        platform="shopify",
        language="en",
        tone="professional",
        status="ready",
        title="Listing",
        description="Description",
        bullet_points="[]",
        seo_title="",
        seo_description="",
        version=1,
        content_hash="x" * 64,
        compliance_status="pass",
        compliance_violations="[]",
    )
    variant = _variant(
        product_id=product_id,
        user_id=user_id,
        sku="TOO-MANY",
        price=39.9,
        attributes={"Color": "Black", "Size": "M", "Material": "ABS", "Style": "Modern"},
    )

    with pytest.raises(ShopifyPublishValidationError, match="三个"):
        build_shopify_product_payload(
            product,
            listing,
            [variant],
            app_url="https://veyaship.com",
        )


@pytest.mark.asyncio
async def test_publish_endpoint_sends_complete_variant_payload(
    client,
    db_session,
    monkeypatch,
):
    email = f"shopify-integrity-{uuid.uuid4().hex[:8]}@test.com"
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": "testpass123"},
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan = "standard"
    await db_session.flush()

    created = await client.post(
        "/api/v1/products/manual",
        json={
            "url": f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
            "title": "Storage Box",
            "price": 12.5,
            "main_image_url": "https://cdn.example.com/product.jpg",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["product"]["id"]

    variant = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json={
            "sku": "BOX-001",
            "attributes": {"Color": "Black"},
            "price": 39.9,
            "cost_price": 12.5,
            "stock_quantity": 8,
        },
        headers=headers,
    )
    assert variant.status_code == 201, variant.text

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "Premium storage box with reinforced handles."

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    generated = await client.post(
        "/api/v1/content/generate",
        json={"product_id": product_id, "platform": "shopify", "language": "en"},
        headers=headers,
    )
    assert generated.status_code == 200, generated.text

    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="integrity-test",
        shop_domain="integrity-test.myshopify.com",
        access_token=encrypt_value("shpat_test"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()

    captured: dict = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, json=None, headers=None, **kwargs):
            captured["url"] = url
            captured["payload"] = json
            return httpx.Response(
                201,
                request=httpx.Request("POST", url),
                json={"product": {"id": 778899}},
            )

    monkeypatch.setattr(shopify_module.httpx, "AsyncClient", FakeClient)
    response = await client.post(
        "/api/v1/shopify/push",
        json={
            "listing_id": generated.json()["listing_id"],
            "channel_id": str(channel.id),
        },
        headers={**headers, "Idempotency-Key": f"integrity-{uuid.uuid4().hex}"},
    )

    assert response.status_code == 200, response.text
    assert "/admin/api/2026-10/products.json" in captured["url"]
    product_payload = captured["payload"]["product"]
    assert product_payload["variants"][0]["price"] == "39.90"
    assert product_payload["variants"][0]["sku"] == "BOX-001"
    assert product_payload["images"][0]["src"] == "https://cdn.example.com/product.jpg"
    assert response.json()["variants_published"] == 1
    assert response.json()["images_published"] == 1

    product_row = (
        await db_session.execute(select(Product).where(Product.id == uuid.UUID(product_id)))
    ).scalar_one()
    listing_row = (
        await db_session.execute(
            select(ListingDraft).where(
                ListingDraft.id == uuid.UUID(generated.json()["listing_id"])
            )
        )
    ).scalar_one()
    direct = await publish_shopify_product(
        db_session,
        user=user,
        product=product_row,
        listing=listing_row,
        channel=channel,
        idempotency_key=f"direct-{uuid.uuid4().hex}",
        app_url="https://veyaship.com",
    )
    assert direct.prepared is not None
    assert direct.prepared.variant_count == 1
    assert direct.publication.status == "completed"


@pytest.mark.asyncio
async def test_shopify_publish_can_select_specific_variants(db_session):
    """指定 variant_ids 时只发布勾选 SKU，不能把其他变体一起带上。"""
    user = User(
        email=f"variant-publish-{uuid.uuid4().hex[:8]}@example.com",
        username="variant-publish",
        password_hash="x",
        plan="standard",
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Variant Product",
        price=10,
    )
    db_session.add(product)
    await db_session.flush()
    selected = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="SELECTED-SKU",
        attributes_json='{"Color":"Black"}',
        price=29.9,
        stock_quantity=5,
        is_active=True,
    )
    ignored = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="IGNORED-SKU",
        attributes_json='{"Color":"White"}',
        price=31.9,
        stock_quantity=8,
        is_active=True,
    )
    db_session.add_all([selected, ignored])
    await db_session.flush()

    variants = await _load_active_variants(
        db_session,
        product,
        user.id,
        variant_ids=[selected.id],
    )

    assert [item.sku for item in variants] == ["SELECTED-SKU"]
    with pytest.raises(ShopifyPublishValidationError, match="不属于当前商品"):
        await _load_active_variants(
            db_session,
            product,
            user.id,
            variant_ids=[uuid.uuid4()],
        )


@pytest.mark.asyncio
async def test_agent_uses_shared_shopify_publish_service(
    db_session,
    monkeypatch,
):
    user = User(
        email=f"agent-shopify-{uuid.uuid4().hex[:8]}@test.com",
        username="agent-shopify",
        password_hash="x",
        plan="standard",
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Agent Shopify Product",
        price=12.5,
    )
    db_session.add(product)
    await db_session.flush()
    listing = await persist_generated_listing(
        db_session,
        user=user,
        product=product,
        platform="shopify",
        language="en",
        tone="professional",
        title="Agent Shopify Listing",
        description="Description",
        bullet_points=["Bullet"],
        seo_title="SEO",
        seo_description="SEO description",
        violations=[],
        blocked=False,
        ai_model_used="test",
    )
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="agent-shared",
        shop_domain="agent-shared.myshopify.com",
        access_token=encrypt_value("shpat_test"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()
    called: dict = {}

    async def fake_publish(db, **kwargs):
        called.update(kwargs)
        publication = SimpleNamespace(
            id=uuid.uuid4(),
            listing_id=listing.id,
            external_product_id="556677",
            external_url="https://agent-shared.myshopify.com/admin/products/556677",
        )
        prepared = PreparedShopifyProduct(
            product={"title": "Agent Shopify Listing"},
            variant_count=1,
            image_count=1,
        )
        return ShopifyPublishResult(publication=publication, prepared=prepared, replayed=False)

    monkeypatch.setattr(
        "app.services.ai.agent_orchestrator.publish_shopify_product",
        fake_publish,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    result = await orchestrator._execute_step(
        "push_to_shopify",
        {"listing_id": str(listing.id), "channel_id": str(channel.id)},
    )

    assert result["status"] == "success"
    assert called["listing"].id == listing.id
    assert called["product"].id == product.id
    assert result["data"]["variants_published"] == 1


@pytest.mark.asyncio
async def test_publish_endpoint_requires_sellable_sku_without_creating_publication(
    client,
    db_session,
):
    email = f"shopify-no-sku-{uuid.uuid4().hex[:8]}@test.com"
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": "testpass123"},
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan = "standard"
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="No SKU Product",
        price=12.5,
    )
    db_session.add(product)
    await db_session.flush()
    listing = await persist_generated_listing(
        db_session,
        user=user,
        product=product,
        platform="shopify",
        language="en",
        tone="professional",
        title="No SKU Listing",
        description="Description",
        bullet_points=["Bullet"],
        seo_title="SEO",
        seo_description="SEO description",
        violations=[],
        blocked=False,
        ai_model_used="test",
    )
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="no-sku",
        shop_domain="no-sku.myshopify.com",
        access_token=encrypt_value("shpat_test"),
        is_active=True,
    )
    db_session.add(channel)
    await db_session.flush()

    response = await client.post(
        "/api/v1/shopify/push",
        json={"listing_id": str(listing.id), "channel_id": str(channel.id)},
        headers={**headers, "Idempotency-Key": f"no-sku-{uuid.uuid4().hex}"},
    )

    assert response.status_code == 409
    assert "启用 SKU" in response.json()["detail"]
    publications = (
        await db_session.execute(
            select(Publication).where(Publication.user_id == user.id)
        )
    ).scalars().all()
    assert publications == []
