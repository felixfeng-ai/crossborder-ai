"""Shopify 商品图片采用动作测试。"""

import base64
import json
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.core.crypto import encrypt_value
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.action_dispatcher import resolve_action_adapter
from app.services.shopify_listing_media_adapter import (
    ShopifyListingMediaActionAdapter,
)
from app.services.workspaces import ensure_personal_workspace


async def _media_context(db_session, tmp_path, email: str):
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
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="shopify",
        title="旅行收纳包",
        content_hash="d" * 64,
        status="published",
    )
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="media-store.myshopify.com",
        shop_domain="media-store.myshopify.com",
        access_token=encrypt_value("shpat_media"),
    )
    db_session.add(product)
    await db_session.flush()
    listing.product_id = product.id
    db_session.add_all([listing, channel])
    await db_session.flush()
    publication = Publication(
        user_id=user.id,
        listing_id=listing.id,
        platform="shopify",
        channel_id=str(channel.id),
        status="completed",
        external_product_id="gid://shopify/Product/700",
    )
    db_session.add(publication)
    storage_key = f"media/{uuid4()}.png"
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=workspace.id,
        name="scene",
        kind="generated",
        storage_key=storage_key,
        content_type="image/png",
        width=12,
        height=12,
        file_size=12,
    )
    target = tmp_path / asset.storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fake-png-bytes")
    db_session.add(asset)
    await db_session.commit()
    return user, workspace, listing, channel, asset


def _transport(state: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/products/700.json"):
            return httpx.Response(
                200,
                json={
                    "product": {
                        "id": 700,
                        "images": state["images"],
                    }
                },
            )
        if request.method == "POST" and path.endswith("/products/700/images.json"):
            body = json.loads(request.content)["image"]
            state["post_count"] += 1
            state["last_attachment"] = body["attachment"]
            image = {
                "id": 8000 + state["post_count"],
                "alt": body.get("alt"),
                "src": f"https://cdn.example/{state['post_count']}.png",
            }
            state["images"].append(image)
            return httpx.Response(
                200,
                json={"image": image},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_listing_media_attach_is_idempotent_and_verified(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user, workspace, listing, channel, asset = await _media_context(
        db_session,
        tmp_path,
        "listing-media@example.com",
    )
    state = {"images": [], "post_count": 0, "last_attachment": None}
    adapter = ShopifyListingMediaActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "asset_ids": [str(asset.id)],
    }

    snapshot = await adapter.preflight(
        action_id="listing.media.attach",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="listing.media.attach",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="media-attach-1",
    )
    verification = await adapter.verify(
        action_id="listing.media.attach",
        target_id=str(listing.id),
        execution=execution,
    )
    replay = await adapter.execute(
        action_id="listing.media.attach",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="media-attach-1",
    )

    assert snapshot["asset_count"] == 1
    assert state["post_count"] == 1
    assert base64.b64decode(state["last_attachment"]) == b"fake-png-bytes"
    assert verification.matched is True
    assert replay.output["uploaded_count"] == 0
    assert listing.main_image_url == f"/api/v1/images/assets/{asset.id}/file"


@pytest.mark.asyncio
async def test_listing_media_rejects_foreign_asset(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user, workspace, listing, channel, _asset = await _media_context(
        db_session,
        tmp_path,
        "listing-media-owner@example.com",
    )
    _other_user, _other_workspace, _listing, _channel, foreign = (
        await _media_context(
            db_session,
            tmp_path,
            "listing-media-other@example.com",
        )
    )
    adapter = ShopifyListingMediaActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport({"images": [], "post_count": 0}),
    )

    with pytest.raises(ValueError, match="图片"):
        await adapter.preflight(
            action_id="listing.media.attach",
            target_id=str(listing.id),
            input_data={
                "channel_id": str(channel.id),
                "asset_ids": [str(foreign.id)],
            },
        )


@pytest.mark.asyncio
async def test_dispatcher_routes_listing_media_action(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user, workspace, listing, _channel, _asset = await _media_context(
        db_session,
        tmp_path,
        "listing-media-dispatch@example.com",
    )
    from app.models.action_run import ActionRun

    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=uuid4(),
        action_id="listing.media.attach",
        platform="shopify",
        target_type="listings",
        target_id=str(listing.id),
        input_json="{}",
        status="queued",
        risk_level="medium",
        autonomy_level="confirm",
        idempotency_key="listing-media-dispatch-1",
    )

    adapter = await resolve_action_adapter(db_session, run)

    assert isinstance(adapter, ShopifyListingMediaActionAdapter)
