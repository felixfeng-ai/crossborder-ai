"""Amazon Listing 标题、描述与卖点 PATCH 测试。"""

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
from app.services.amazon_listing_content_adapter import (
    AmazonListingContentUpdateAdapter,
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
        title="Amazon Content Product",
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
    )
    db_session.add_all([connection, product])
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        sku="AMZ-CONTENT-01",
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
        title="Old Amazon Title",
        description="Old description",
        bullet_points=json.dumps(["Old bullet 1", "Old bullet 2"]),
        content_hash="b" * 64,
        compliance_status="passed",
        version=3,
    )
    db_session.add_all([variant, listing])
    await db_session.commit()
    await db_session.refresh(variant)
    await db_session.refresh(listing)
    return user, workspace, connection, variant, listing


class FakeContentService:
    def __init__(self):
        self.title = "Old Amazon Title"
        self.description = "Old description"
        self.bullets = ["Old bullet 1", "Old bullet 2"]
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
            "attributes": {
                "item_name": [
                    {
                        "value": self.title,
                        "language_tag": "en_US",
                    }
                ],
                "product_description": [
                    {
                        "value": self.description,
                        "language_tag": "en_US",
                    }
                ],
                "bullet_point": [
                    {
                        "value": item,
                        "language_tag": "en_US",
                    }
                    for item in self.bullets
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
        for patch in kwargs["patches"]:
            values = [
                item.get("value")
                for item in patch["value"]
                if isinstance(item, dict)
            ]
            if patch["path"].endswith("item_name"):
                self.title = values[0]
            elif patch["path"].endswith("product_description"):
                self.description = values[0]
            elif patch["path"].endswith("bullet_point"):
                self.bullets = values
        return {"status": "ACCEPTED", "issues": []}


@pytest.mark.asyncio
async def test_content_update_preflight_execute_verify_and_local_version(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-content-update@example.com",
    )
    service = FakeContentService()

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch.setattr(
        "app.services.amazon_listing_publish.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    adapter = AmazonListingContentUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "listing_id": str(listing.id),
        "variant_id": str(variant.id),
        "marketplace_id": "ATVPDKIKX0DER",
        "title": "New Amazon Title",
        "description": "New description",
        "bullet_points": ["New bullet 1", "New bullet 2", "New bullet 3"],
    }
    before = await adapter.preflight(
        action_id="amazon.listings.update",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="amazon.listings.update",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="amazon-content-1",
    )
    verification = await adapter.verify(
        action_id="amazon.listings.update",
        target_id=str(listing.id),
        execution=execution,
    )
    await db_session.refresh(listing)

    assert before["changed_fields"] == [
        "title",
        "description",
        "bullet_points",
    ]
    assert service.preview_calls == 1
    paths = {
        patch["path"]
        for patch in service.patches[0]
    }
    assert paths == {
        "/attributes/item_name",
        "/attributes/product_description",
        "/attributes/bullet_point",
    }
    assert verification.matched is True
    assert listing.title == "New Amazon Title"
    assert listing.version == 4
    assert listing.compliance_status == "unknown"


@pytest.mark.asyncio
async def test_content_update_rejects_invalid_or_empty_changes(db_session):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-content-invalid@example.com",
    )
    adapter = AmazonListingContentUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeContentService(),
    )
    with pytest.raises(ValueError, match="至少"):
        await adapter.preflight(
            action_id="amazon.listings.update",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
            },
        )
    with pytest.raises(ValueError, match="200"):
        await adapter.preflight(
            action_id="amazon.listings.update",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "title": "X" * 201,
            },
        )


@pytest.mark.asyncio
async def test_content_update_preview_lists_changed_fields(db_session):
    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-content-preview@example.com",
    )
    from app.models.action_run import ActionRun

    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=uuid.uuid4(),
        action_id="amazon.listings.update",
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
                "changed_fields": ["title", "bullet_points"],
            }
        ),
        status="awaiting_confirmation",
        risk_level="medium",
        autonomy_level="confirm",
        idempotency_key="amazon-content-preview-1",
    )
    preview = build_action_preview(
        run,
        fallback_title="Update Amazon Listing",
    )
    assert preview.title == "即将更新 Amazon Listing"
    assert any(
        field.label == "修改字段" and "标题" in field.value
        for field in preview.fields
    )


@pytest.mark.asyncio
async def test_agent_prepares_amazon_listing_content_update(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, _connection, variant, listing = await _context(
        db_session,
        "amazon-content-agent@example.com",
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
            "changed_fields": ["title", "description"],
            "preview_status": "VALIDATION_PREVIEW",
        }

    monkeypatch.setattr(
        AmazonListingContentUpdateAdapter,
        "preflight",
        fake_preflight,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "update_amazon_listing",
        {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": "ATVPDKIKX0DER",
            "title": "New Amazon Title",
            "description": "New description",
        },
    )
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "amazon.listings.update"
    assert pending["params"]["title"] == "New Amazon Title"
