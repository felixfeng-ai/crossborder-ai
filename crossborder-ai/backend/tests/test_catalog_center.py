"""SKU / 变体 / Listing 中心行为。"""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.platform_rules import validate_listing_for_platform


async def _current_user(db_session, email: str = "test@example.com") -> User:
    return (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()


async def _seed_catalog(db_session) -> tuple[Product, ProductVariant, ListingDraft]:
    user = await _current_user(db_session)
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/catalog-{uuid.uuid4().hex}.html",
        title="Catalog Test Bottle",
        price=20,
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="CATALOG-001",
        name="Black M",
        attributes_json=json.dumps({"颜色": "灰色", "尺寸": "XL"}, ensure_ascii=False),
        price=29.9,
        cost_price=12.5,
        stock_quantity=20,
        is_active=True,
    )
    listing = ListingDraft(
        user_id=user.id,
        product_id=product.id,
        platform="amazon",
        language="en",
        tone="professional",
        status="ready",
        title="Stainless Steel Insulated Bottle 500ml",
        description="<p>A practical insulated bottle for daily commuting.</p>",
        bullet_points=json.dumps(
            [
                "Keeps drinks cold",
                "Leak-proof lid",
                "Fits most cup holders",
                "Easy to clean",
                "Durable stainless steel",
            ],
            ensure_ascii=False,
        ),
        seo_title="Insulated Bottle",
        seo_description="Portable insulated bottle for commuting.",
        version=1,
        content_hash=uuid.uuid4().hex,
        compliance_status="pass",
        compliance_violations="[]",
    )
    db_session.add_all([variant, listing])
    await db_session.flush()
    return product, variant, listing


@pytest.mark.asyncio
async def test_global_variant_list_and_filters(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    product, variant, _ = await _seed_catalog(db_session)

    response = await client.get(
        "/api/v1/catalog/variants",
        params={"search": "Catalog Test", "low_stock": False},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert any(item["id"] == str(variant.id) for item in items)
    item = next(item for item in items if item["id"] == str(variant.id))
    assert item["product_title"] == product.title
    assert item["attributes"]["尺寸"] == "XL"


@pytest.mark.asyncio
async def test_variant_matrix_is_idempotent(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    product, _, _ = await _seed_catalog(db_session)
    payload = {
        "attribute_groups": {
            "颜色": ["黑色", "白色"],
            "尺寸": ["M", "L"],
        },
        "sku_prefix": "BOTTLE",
        "price": 39.9,
        "cost_price": 15.0,
        "stock_quantity": 8,
    }

    first = await client.post(
        f"/api/v1/catalog/products/{product.id}/variants/generate",
        json=payload,
        headers=auth_headers,
    )
    second = await client.post(
        f"/api/v1/catalog/products/{product.id}/variants/generate",
        json=payload,
        headers=auth_headers,
    )

    assert first.status_code == 201, first.text
    assert first.json()["created"] == 4
    assert second.status_code == 201, second.text
    assert second.json()["created"] == 0
    assert second.json()["skipped"] == 4

    variants = (
        await db_session.execute(
            select(ProductVariant).where(ProductVariant.product_id == product.id)
        )
    ).scalars().all()
    generated = [item for item in variants if item.sku.startswith("BOTTLE-")]
    assert len(generated) == 4
    assert len({item.sku for item in generated}) == 4


@pytest.mark.asyncio
async def test_bulk_variant_update_is_atomic_across_users(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    _, own_variant, _ = await _seed_catalog(db_session)
    other_user = User(
        email=f"catalog-other-{uuid.uuid4().hex[:6]}@example.com",
        username="catalog-other",
        password_hash="x",
    )
    db_session.add(other_user)
    await db_session.flush()
    other_product = Product(
        user_id=other_user.id,
        url=f"https://detail.1688.com/offer/other-{uuid.uuid4().hex}.html",
        title="Other Product",
    )
    db_session.add(other_product)
    await db_session.flush()
    other_variant = ProductVariant(
        user_id=other_user.id,
        product_id=other_product.id,
        sku=f"OTHER-{uuid.uuid4().hex[:6]}",
        stock_quantity=3,
    )
    db_session.add(other_variant)
    await db_session.flush()

    response = await client.patch(
        "/api/v1/catalog/variants/bulk",
        json={
            "variant_ids": [str(own_variant.id), str(other_variant.id)],
            "price": 49.9,
            "stock_quantity": 7,
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    await db_session.refresh(own_variant)
    assert own_variant.price == 29.9
    assert own_variant.stock_quantity == 20


@pytest.mark.asyncio
async def test_global_listing_list_contains_readiness(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    _, _, listing = await _seed_catalog(db_session)

    response = await client.get(
        "/api/v1/catalog/listings",
        params={"platform": "amazon"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    item = next(
        item for item in response.json()["items"] if item["id"] == str(listing.id)
    )
    assert item["platform"] == "amazon"
    assert item["readiness"]["ok"] is True
    assert item["readiness"]["checks"]


def test_platform_rules_validate_title_and_bullets():
    result = validate_listing_for_platform(
        "amazon",
        {
            "title": "",
            "description": "<p>Description</p>",
            "bullet_points": ["Only one"],
            "seo_title": "",
            "seo_description": "",
        },
    )

    statuses = {check["id"]: check["status"] for check in result["checks"]}
    assert result["ok"] is False
    assert statuses["title"] == "error"
    assert statuses["bullets"] == "warning"
