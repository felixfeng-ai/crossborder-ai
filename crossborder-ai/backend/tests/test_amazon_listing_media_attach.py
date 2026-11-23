"""Amazon Listing 持久图片 URL 绑定测试。"""

import json
import uuid

import pytest

from app.core.crypto import encrypt_value
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.action_previews import build_action_preview
from app.services.amazon_listing_media_adapter import (
    AmazonListingMediaAttachAdapter,
)
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
        title="Amazon Media Product",
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
    )
    db_session.add_all([connection, product])
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        sku="AMZ-MEDIA-01",
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
        title="Amazon Media Product",
        description="Description",
        content_hash="c" * 64,
        compliance_status="passed",
        version=2,
    )
    db_session.add_all([variant, listing])
    await db_session.commit()
    await db_session.refresh(variant)
    await db_session.refresh(listing)
    return user, workspace, connection, variant, listing


class FakeMediaService:
    def __init__(self):
        self.attributes = {}
        self.preview_calls = 0
        self.patches = []

    async def get_listing(self, **kwargs):
        return {
            "summaries": [
                {
                    "marketplaceId": kwargs["marketplace_id"],
                    "productType": "HOME_FRAGRANCE",
                }
            ],
            "attributes": dict(self.attributes),
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
        for patch in kwargs["patches"]:
            key = patch["path"].rsplit("/", 1)[-1]
            self.attributes[key] = patch["value"]
        return {"status": "ACCEPTED", "issues": []}


@pytest.mark.asyncio
async def test_media_attach_preflight_execute_verify(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-media-attach@example.com",
    )
    service = FakeMediaService()

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch.setattr(
        "app.services.amazon_listing_publish.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    adapter = AmazonListingMediaAttachAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "listing_id": str(listing.id),
        "variant_id": str(variant.id),
        "marketplace_id": "ATVPDKIKX0DER",
        "main_image_url": "https://cdn.example.com/main.jpg",
        "other_image_urls": [
            "https://cdn.example.com/2.jpg",
            "s3://my-bucket/3.jpg",
        ],
    }
    before = await adapter.preflight(
        action_id="amazon.listing.media.attach",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="amazon.listing.media.attach",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="amazon-media-1",
    )
    verification = await adapter.verify(
        action_id="amazon.listing.media.attach",
        target_id=str(listing.id),
        execution=execution,
    )

    assert before["image_count"] == 3
    assert service.preview_calls == 1
    paths = {
        patch["path"]
        for patch in service.patches[0]
    }
    assert paths == {
        "/attributes/main_product_image_locator",
        "/attributes/other_product_image_locator_1",
        "/attributes/other_product_image_locator_2",
    }
    assert verification.matched is True
    assert verification.snapshot["image_count"] == 3


@pytest.mark.asyncio
async def test_media_attach_rejects_private_or_temporary_urls(db_session):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-media-invalid@example.com",
    )
    adapter = AmazonListingMediaAttachAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeMediaService(),
    )
    for url in [
        "http://cdn.example.com/main.jpg",
        "https://localhost/main.jpg",
        "https://127.0.0.1/main.jpg",
        "C:/images/main.jpg",
        "https://cdn.example.com/main.jpg?X-Amz-Signature=abc",
    ]:
        with pytest.raises(ValueError, match="图片"):
            await adapter.preflight(
                action_id="amazon.listing.media.attach",
                target_id=str(listing.id),
                input_data={
                    "variant_id": str(variant.id),
                    "marketplace_id": "ATVPDKIKX0DER",
                    "main_image_url": url,
                },
            )


@pytest.mark.asyncio
async def test_media_attach_preview_shows_image_count(db_session):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-media-preview@example.com",
    )
    from app.models.action_run import ActionRun

    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=uuid.uuid4(),
        action_id="amazon.listing.media.attach",
        action_version="1.0",
        platform="amazon",
        target_type="listing",
        target_id=str(listing.id),
        input_json=json.dumps(
            {
                "listing_id": str(listing.id),
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "sku": variant.sku,
                "image_count": 3,
            }
        ),
        status="awaiting_confirmation",
        risk_level="medium",
        autonomy_level="confirm",
        idempotency_key="amazon-media-preview-1",
    )
    preview = build_action_preview(
        run,
        fallback_title="Attach Amazon Media",
    )
    assert preview.title == "即将绑定 Amazon Listing 图片"
    assert any(
        field.label == "图片" and field.value == "3 张"
        for field in preview.fields
    )


@pytest.mark.asyncio
async def test_agent_prepares_amazon_media_attach(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-media-agent@example.com",
    )

    async def fake_preflight(
        self,
        *,
        action_id,
        target_id,
        input_data,
    ):
        return {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "marketplace_id": input_data["marketplace_id"],
            "product_type": "HOME_FRAGRANCE",
            "image_count": 2,
            "preview_status": "VALIDATION_PREVIEW",
        }

    monkeypatch.setattr(
        AmazonListingMediaAttachAdapter,
        "preflight",
        fake_preflight,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "attach_amazon_listing_images",
        {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": "ATVPDKIKX0DER",
            "main_image_url": "https://cdn.example.com/main.jpg",
            "other_image_urls": ["https://cdn.example.com/2.jpg"],
        },
    )
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "amazon.listing.media.attach"
    assert pending["params"]["image_count"] == 2
