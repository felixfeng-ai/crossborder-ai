"""Amazon SP-API Listing 预览与发布测试。"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import MarketingCampaignPublication
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.user import User
from app.services.amazon_listing_publish import (
    AmazonListingPublishError,
    AmazonListingPublishService,
    build_amazon_listing_payload,
)
import app.services.amazon_listing_publish as amazon_listing_module


def test_build_amazon_listing_payload_uses_real_sku_price_and_bullets():
    product = Product(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        url="https://example.com/product",
        title="DONMIS 香薰礼盒",
        brand_name="DONMIS",
    )
    variant = ProductVariant(
        id=uuid.uuid4(),
        user_id=product.user_id,
        product_id=product.id,
        sku="DONMIS-GIFT-01",
        price=39.9,
        stock_quantity=25,
        is_active=True,
    )
    from app.models.listing_draft import ListingDraft

    listing = ListingDraft(
        id=uuid.uuid4(),
        user_id=product.user_id,
        product_id=product.id,
        platform="amazon",
        language="en",
        tone="marketing",
        status="ready",
        title="DONMIS Scented Sachet Gift Set",
        description="A festive scented sachet gift set.",
        bullet_points='["Long-lasting fragrance","Ready for gifting"]',
        seo_title="DONMIS gift set",
        seo_description="Festive fragrance gift",
        version=1,
        content_hash="hash",
        compliance_status="pass",
    )

    payload = build_amazon_listing_payload(
        product,
        listing,
        variant,
        product_type="HOME_FRAGRANCE",
        marketplace_id="ATVPDKIKX0DER",
        language_tag="en_US",
    )

    assert payload["productType"] == "HOME_FRAGRANCE"
    assert payload["attributes"]["item_name"][0]["value"] == (
        "DONMIS Scented Sachet Gift Set"
    )
    assert len(payload["attributes"]["bullet_point"]) == 2
    assert payload["attributes"]["purchasable_offer"][0][
        "our_price"
    ][0]["schedule"][0]["value_with_tax"] == 39.9


@pytest.mark.asyncio
async def test_amazon_submit_uses_validation_preview_and_writes_headers(
    monkeypatch,
):
    captured = {}

    async def fake_refresh(self, refresh_token):
        assert refresh_token == "Atzr|test"
        return "Atza|access"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def put(self, url, *, params, json, headers):
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
                request=httpx.Request("PUT", url),
                json={"status": "INVALID", "submissionId": "preview-1", "issues": []},
            )

    monkeypatch.setattr(
        amazon_listing_module.AmazonSpApiService,
        "refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(amazon_listing_module.httpx, "AsyncClient", FakeClient)

    result = await AmazonListingPublishService().submit_listing(
        refresh_token="Atzr|test",
        seller_id="A1SELLER",
        marketplace_id="ATVPDKIKX0DER",
        sku="AMZ-DONMIS-01",
        payload={"productType": "HOME_FRAGRANCE", "attributes": {}},
        preview=True,
    )

    assert result["submissionId"] == "preview-1"
    assert captured["url"].endswith("/A1SELLER/AMZ-DONMIS-01")
    assert captured["params"] == {
        "marketplaceIds": "ATVPDKIKX0DER",
        "mode": "VALIDATION_PREVIEW",
    }
    assert captured["headers"]["x-amz-access-token"] == "Atza|access"


@pytest.mark.asyncio
async def test_amazon_submit_maps_permission_error(monkeypatch):
    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def put(self, url, *, params, json, headers):
            return httpx.Response(
                403,
                request=httpx.Request("PUT", url),
                json={"issues": [{"code": "Unauthorized"}]},
            )

    monkeypatch.setattr(
        amazon_listing_module.AmazonSpApiService,
        "refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(amazon_listing_module.httpx, "AsyncClient", FakeClient)

    with pytest.raises(AmazonListingPublishError, match="Listings Items 权限"):
        await AmazonListingPublishService().submit_listing(
            refresh_token="Atzr|test",
            seller_id="A1SELLER",
            marketplace_id="ATVPDKIKX0DER",
            sku="AMZ-DONMIS-01",
            payload={"productType": "HOME_FRAGRANCE", "attributes": {}},
            preview=False,
        )


async def _amazon_context(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    await db_session.flush()
    channel = PlatformConnection(
        user_id=user.id,
        platform="amazon",
        account_name="Amazon US",
        external_account_id="A1SELLER",
        marketplace_id="ATVPDKIKX0DER",
        credentials=encrypt_value('{"refresh_token":"Atzr|test"}'),
        status="active",
    )
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Amazon Listing Product",
        brand_name="DONMIS",
    )
    db_session.add_all([channel, product])
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="AMZ-DONMIS-01",
        price=49.9,
        stock_quantity=12,
        is_active=True,
    )
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="Amazon 发布活动",
        objective="conversion",
        platform="amazon",
        market="US",
        language="en",
        budget_credits=200,
        brief_json="{}",
    )
    db_session.add_all([variant, campaign])
    await db_session.flush()
    copy_asset = MarketingCopyAsset(
        batch_id=uuid.uuid4(),
        user_id=user.id,
        campaign_id=campaign.id,
        platform="amazon",
        variant_key="A",
        language="en",
        headline="DONMIS Scented Sachet Gift Set",
        body="A festive scented sachet gift set.",
        cta="Gift it",
        compliance_status="pass",
    )
    db_session.add(copy_asset)
    await db_session.flush()
    return user, channel, product, variant, campaign, copy_asset


@pytest.mark.asyncio
async def test_amazon_listing_preview_returns_real_issues(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    _, channel, _, _, campaign, copy_asset = await _amazon_context(db_session)

    captured = {}

    async def fake_submit(self, **kwargs):
        captured.update(kwargs)
        return {
            "status": "INVALID",
            "submissionId": "preview-1",
            "issues": [
                {
                    "code": "90220",
                    "severity": "ERROR",
                    "message": "缺少商品类型必填属性",
                    "attributeNames": ["country_of_origin"],
                }
            ],
        }

    monkeypatch.setattr(AmazonListingPublishService, "submit_listing", fake_submit)

    response = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/publications",
        json={
            "platform": "amazon",
            "copy_id": str(copy_asset.id),
            "channel_id": str(channel.id),
            "product_type": "HOME_FRAGRANCE",
            "preview": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "INVALID"
    assert response.json()["issues"][0]["attributeNames"] == ["country_of_origin"]
    assert captured["sku"] == "AMZ-DONMIS-01"
    assert captured["seller_id"] == "A1SELLER"


@pytest.mark.asyncio
async def test_amazon_listing_publish_records_accepted_submission(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    user, channel, _, _, campaign, copy_asset = await _amazon_context(db_session)

    async def fake_submit(self, **kwargs):
        return {
            "status": "ACCEPTED",
            "submissionId": "submission-1",
            "issues": [],
        }

    monkeypatch.setattr(AmazonListingPublishService, "submit_listing", fake_submit)

    response = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/publications",
        json={
            "platform": "amazon",
            "copy_id": str(copy_asset.id),
            "channel_id": str(channel.id),
            "product_type": "HOME_FRAGRANCE",
            "preview": False,
        },
        headers={
            **auth_headers,
            "Idempotency-Key": "amazon-publish-1",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["external_product_id"] == "AMZ-DONMIS-01"
    publication = (
        await db_session.execute(
            select(Publication).where(
                Publication.user_id == user.id,
                Publication.platform == "amazon",
            )
        )
    ).scalar_one()
    assert publication.status == "completed"
    record = (
        await db_session.execute(
            select(MarketingCampaignPublication).where(
                MarketingCampaignPublication.campaign_id == campaign.id,
                MarketingCampaignPublication.platform == "amazon",
            )
        )
    ).scalar_one()
    assert record.status == "completed"
    assert record.external_product_id == "AMZ-DONMIS-01"


@pytest.mark.asyncio
async def test_amazon_permission_error_is_not_marked_completed(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    _, channel, _, _, campaign, copy_asset = await _amazon_context(db_session)

    async def fake_submit(self, **kwargs):
        raise AmazonListingPublishError(
            "Amazon 应用缺少 Listings Items 权限",
            status_code=403,
        )

    monkeypatch.setattr(AmazonListingPublishService, "submit_listing", fake_submit)

    response = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/publications",
        json={
            "platform": "amazon",
            "copy_id": str(copy_asset.id),
            "channel_id": str(channel.id),
            "product_type": "HOME_FRAGRANCE",
            "preview": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 403
    record = (
        await db_session.execute(
            select(MarketingCampaignPublication).where(
                MarketingCampaignPublication.campaign_id == campaign.id,
                MarketingCampaignPublication.platform == "amazon",
            )
        )
    ).scalar_one()
    assert record.status == "failed"
    assert "Listings Items" in (record.error or "")


@pytest.mark.asyncio
async def test_amazon_capability_now_supports_publish(client):
    response = await client.get("/api/v1/platforms/capabilities")
    assert response.status_code == 200
    amazon = response.json()["platforms"]["amazon"]
    assert amazon["publish_supported"] is True
    assert "Listings Items" in amazon["reason"]
