"""Amazon Listing 工作区素材发布与图片绑定闭环测试。"""

import json
import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.crypto import encrypt_value
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.amazon_listing_asset_media_adapter import (
    AmazonListingAssetMediaAdapter,
)
from app.services.workspaces import ensure_personal_workspace


class FakePublicStorage:
    def __init__(self):
        self.keys = []

    async def put_bytes(self, key, data, *, content_type):
        self.keys.append((key, data, content_type))
        return f"https://cdn.example.com/{key}"


class FakeMediaService:
    def __init__(self):
        self.attributes = {}
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


async def _context(
    db_session,
    tmp_path: Path,
    email: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
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
        title="Asset Media Product",
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
    )
    db_session.add_all([connection, product])
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        sku="AMZ-ASSET-MEDIA-01",
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
        title="Asset Media Product",
        description="Description",
        content_hash="d" * 64,
        compliance_status="passed",
        version=2,
    )
    db_session.add_all([variant, listing])
    await db_session.flush()
    assets = []
    for index in range(2):
        asset_id = uuid.uuid4()
        storage_key = f"assets/{asset_id}.webp"
        target = tmp_path / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"image-{index}".encode())
        asset = ImageAsset(
            id=asset_id,
            user_id=user.id,
            workspace_id=workspace.id,
            name=f"Image {index}",
            kind="upload",
            storage_key=storage_key,
            content_type="image/webp",
            width=800,
            height=800,
            file_size=7,
        )
        db_session.add(asset)
        assets.append(asset)
    await db_session.commit()
    for item in [variant, listing, *assets]:
        await db_session.refresh(item)
    return user, workspace, variant, listing, assets


@pytest.mark.asyncio
async def test_asset_media_preflight_execute_and_verify(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, variant, listing, assets = await _context(
        db_session,
        tmp_path,
        "amazon-asset-media@example.com",
        monkeypatch,
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    monkeypatch.setattr(
        "app.services.amazon_listing_publish.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    media_service = FakeMediaService()
    public_storage = FakePublicStorage()
    adapter = AmazonListingAssetMediaAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        media_service=media_service,
        public_storage=public_storage,
    )
    input_data = {
        "listing_id": str(listing.id),
        "variant_id": str(variant.id),
        "marketplace_id": "ATVPDKIKX0DER",
        "asset_ids": [str(item.id) for item in assets],
    }
    before = await adapter.preflight(
        action_id="amazon.listing.media.attach_assets",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="amazon.listing.media.attach_assets",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="amazon-asset-media-1",
    )
    verification = await adapter.verify(
        action_id="amazon.listing.media.attach_assets",
        target_id=str(listing.id),
        execution=execution,
    )

    assert before["asset_count"] == 2
    assert [item[0] for item in public_storage.keys] == [
        f"{workspace.id}/{assets[0].id}.webp",
        f"{workspace.id}/{assets[1].id}.webp",
    ]
    assert public_storage.keys[0][1] == b"image-0"
    assert media_service.preview_calls == 1
    assert verification.matched is True
    assert verification.snapshot["image_count"] == 2


@pytest.mark.asyncio
async def test_asset_media_rejects_foreign_deleted_or_too_many_assets(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, variant, listing, assets = await _context(
        db_session,
        tmp_path,
        "amazon-asset-invalid@example.com",
        monkeypatch,
    )
    adapter = AmazonListingAssetMediaAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        media_service=FakeMediaService(),
        public_storage=FakePublicStorage(),
    )
    with pytest.raises(ValueError, match="1 至 9"):
        await adapter.preflight(
            action_id="amazon.listing.media.attach_assets",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "asset_ids": [],
            },
        )
    with pytest.raises(ValueError, match="1 至 9"):
        await adapter.preflight(
            action_id="amazon.listing.media.attach_assets",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "asset_ids": [str(uuid.uuid4()) for _ in range(10)],
            },
        )
    foreign_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="素材"):
        await adapter.preflight(
            action_id="amazon.listing.media.attach_assets",
            target_id=str(listing.id),
            input_data={
                "variant_id": str(variant.id),
                "marketplace_id": "ATVPDKIKX0DER",
                "asset_ids": [foreign_id],
            },
        )


@pytest.mark.asyncio
async def test_agent_prepares_asset_media_action(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, variant, listing, assets = await _context(
        db_session,
        tmp_path,
        "amazon-asset-media-agent@example.com",
        monkeypatch,
    )

    async def fake_preflight(
        self,
        *,
        action_id,
        target_id,
        input_data,
    ):
        return {
            "asset_count": 2,
            "public_visibility": True,
        }

    monkeypatch.setattr(
        AmazonListingAssetMediaAdapter,
        "preflight",
        fake_preflight,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "attach_amazon_listing_assets",
        {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": "ATVPDKIKX0DER",
            "asset_ids": [str(item.id) for item in assets],
        },
    )
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "amazon.listing.media.attach_assets"
    assert pending["params"]["asset_count"] == 2
