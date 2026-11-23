"""Amazon Listing 库存与售价 PATCH 动作测试。"""

import json
import uuid

import httpx
import pytest

from app.core.crypto import encrypt_value
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.amazon_listing_publish import AmazonListingPublishService
from app.services.amazon_offer_adapter import AmazonOfferUpdateAdapter
from app.services.workspaces import ensure_personal_workspace


async def _context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    connection = PlatformConnection(
        user_id=user.id,
        platform="amazon",
        account_name="Amazon US",
        external_account_id="A1SELLER",
        marketplace_id="ATVPDKIKX0DER",
        credentials=encrypt_value(
            json.dumps({"refresh_token": "Atzr|refresh-token"})
        ),
        status="active",
    )
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        title="Amazon Offer Product",
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
    )
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        sku="AMZ-OFFER-01",
        price=29.9,
        stock_quantity=10,
        is_active=True,
    )
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        platform="amazon",
        language="en",
        tone="professional",
        status="published",
        title="Amazon Offer Product",
        content_hash="a" * 64,
        compliance_status="passed",
        version=2,
    )
    db_session.add_all([connection, product])
    await db_session.flush()
    variant.product_id = product.id
    listing.product_id = product.id
    db_session.add_all([variant, listing])
    await db_session.commit()
    await db_session.refresh(connection)
    await db_session.refresh(variant)
    await db_session.refresh(listing)
    return user, workspace, connection, variant, listing


@pytest.mark.asyncio
async def test_patch_listing_uses_partial_patch_and_preview(monkeypatch):
    captured = {}

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def patch(self, url, *, params, json, headers):
            captured.update(
                {
                    "url": url,
                    "params": params,
                    "json": json,
                    "headers": headers,
                }
            )
            return httpx.Response(
                200,
                request=httpx.Request("PATCH", url),
                json={
                    "status": "VALIDATION_PREVIEW",
                    "submissionId": "patch-preview",
                    "issues": [],
                },
            )

    monkeypatch.setattr(
        "app.services.amazon_listing_publish.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(
        "app.services.amazon_listing_publish.httpx.AsyncClient",
        FakeClient,
    )
    result = await AmazonListingPublishService().patch_listing(
        refresh_token="Atzr|refresh-token",
        seller_id="A1SELLER",
        marketplace_id="ATVPDKIKX0DER",
        sku="AMZ-OFFER-01",
        product_type="HOME_FRAGRANCE",
        patches=[
            {
                "op": "replace",
                "path": "/attributes/fulfillment_availability",
                "value": [
                    {
                        "fulfillment_channel_code": "DEFAULT",
                        "quantity": 20,
                    }
                ],
            }
        ],
        preview=True,
    )

    assert result["status"] == "VALIDATION_PREVIEW"
    assert captured["url"].startswith(
        "https://sellingpartnerapi-na.amazon.com/listings/2021-08-01/items/"
    )
    assert captured["params"] == {
        "marketplaceIds": "ATVPDKIKX0DER",
        "includedData": "issues",
        "mode": "VALIDATION_PREVIEW",
    }
    assert captured["json"]["productType"] == "HOME_FRAGRANCE"
    assert captured["json"]["patches"][0]["path"].endswith(
        "fulfillment_availability"
    )


class FakeListingService:
    def __init__(self, *, stock: int = 10, price: float = 29.9):
        self.stock = stock
        self.price = price
        self.patches = []
        self.preview_calls = 0

    async def get_listing(self, **kwargs):
        return {
            "summaries": [
                {
                    "marketplaceId": kwargs["marketplace_id"],
                    "productType": "HOME_FRAGRANCE",
                }
            ],
            "attributes": {
                "fulfillment_availability": [
                    {
                        "fulfillment_channel_code": "DEFAULT",
                        "quantity": self.stock,
                    }
                ],
                "purchasable_offer": [
                    {
                        "marketplace_id": kwargs["marketplace_id"],
                        "currency": "USD",
                        "our_price": [
                            {
                                "schedule": [
                                    {"value_with_tax": self.price}
                                ]
                            }
                        ],
                    }
                ],
            },
            "issues": [],
        }

    async def patch_listing(self, **kwargs):
        if kwargs["preview"]:
            self.preview_calls += 1
            return {
                "status": "VALIDATION_PREVIEW",
                "issues": [],
            }
        self.patches.append(kwargs["patches"])
        if kwargs["patches"][0]["path"].endswith(
            "fulfillment_availability"
        ):
            self.stock = kwargs["patches"][0]["value"][0]["quantity"]
        else:
            self.price = kwargs["patches"][0]["value"][0]["our_price"][0][
                "schedule"
            ][0]["value_with_tax"]
        return {"status": "ACCEPTED", "issues": []}


@pytest.mark.asyncio
async def test_inventory_action_preflight_execute_and_verify(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.action_runtime import ActionExecution

    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-offer-inventory@example.com",
    )
    service = FakeListingService(stock=10)

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch.setattr(
        "app.services.amazon_listing_publish.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    adapter = AmazonOfferUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "listing_id": str(listing.id),
        "variant_id": str(variant.id),
        "marketplace_id": "ATVPDKIKX0DER",
        "stock_quantity": 25,
    }
    before = await adapter.preflight(
        action_id="amazon.inventory.update",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="amazon.inventory.update",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="amazon-inventory-1",
    )
    verification = await adapter.verify(
        action_id="amazon.inventory.update",
        target_id=str(listing.id),
        execution=execution,
    )

    assert before["before_value"] == "10"
    assert before["after_value"] == "25"
    assert service.preview_calls == 1
    assert len(service.patches) == 1
    assert service.patches[0][0]["value"] == [
        {"fulfillment_channel_code": "DEFAULT", "quantity": 25}
    ]
    assert verification.matched is True
    assert verification.snapshot["stock_quantity"] == 25


@pytest.mark.asyncio
async def test_pricing_action_builds_only_purchasable_offer_patch(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-offer-price@example.com",
    )
    service = FakeListingService(price=29.9)

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch.setattr(
        "app.services.amazon_listing_publish.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    adapter = AmazonOfferUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "listing_id": str(listing.id),
        "variant_id": str(variant.id),
        "marketplace_id": "ATVPDKIKX0DER",
        "price": 39.9,
        "currency": "USD",
    }
    before = await adapter.preflight(
        action_id="amazon.pricing.update",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="amazon.pricing.update",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="amazon-pricing-1",
    )
    verification = await adapter.verify(
        action_id="amazon.pricing.update",
        target_id=str(listing.id),
        execution=execution,
    )

    assert before["before_value"] == "29.90 USD"
    assert before["after_value"] == "39.90 USD"
    assert service.patches[0][0]["path"] == (
        "/attributes/purchasable_offer"
    )
    assert verification.snapshot["price"] == 39.9


@pytest.mark.asyncio
async def test_offer_action_rejects_invalid_values(db_session):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-offer-invalid@example.com",
    )
    adapter = AmazonOfferUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeListingService(),
    )
    with pytest.raises(ValueError, match="库存"):
        await adapter.preflight(
            action_id="amazon.inventory.update",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "stock_quantity": -1,
            },
        )
    with pytest.raises(ValueError, match="售价"):
        await adapter.preflight(
            action_id="amazon.pricing.update",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "price": 0,
                "currency": "USD",
            },
        )


@pytest.mark.asyncio
async def test_agent_prepares_amazon_inventory_and_price_actions(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-offer-agent@example.com",
    )

    async def fake_preflight(
        self,
        *,
        action_id,
        target_id,
        input_data,
    ):
        is_inventory = action_id == "amazon.inventory.update"
        return {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "marketplace_id": input_data["marketplace_id"],
            "product_type": "HOME_FRAGRANCE",
            "attribute_path": (
                "/attributes/fulfillment_availability"
                if is_inventory
                else "/attributes/purchasable_offer"
            ),
            "before_value": "10" if is_inventory else "29.90 USD",
            "after_value": (
                str(input_data["stock_quantity"])
                if is_inventory
                else f"{float(input_data['price']):.2f} USD"
            ),
            "preview_status": "VALIDATION_PREVIEW",
        }

    monkeypatch.setattr(
        AmazonOfferUpdateAdapter,
        "preflight",
        fake_preflight,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    inventory = await orchestrator._execute_step(
        "update_amazon_inventory",
        {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": "ATVPDKIKX0DER",
            "stock_quantity": 25,
        },
    )
    price = await orchestrator._execute_step(
        "update_amazon_price",
        {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": "ATVPDKIKX0DER",
            "price": 39.9,
            "currency": "USD",
        },
    )

    assert inventory["data"]["pending_action"]["action"] == (
        "amazon.inventory.update"
    )
    assert inventory["data"]["pending_action"]["params"]["stock_quantity"] == 25
    assert price["data"]["pending_action"]["action"] == (
        "amazon.pricing.update"
    )
    assert price["data"]["pending_action"]["params"]["price"] == 39.9
