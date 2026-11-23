"""Shopify 已上架商品内容更新动作测试。"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.action_dispatcher import resolve_action_adapter
from app.services.shopify_listing_update_adapter import (
    ShopifyListingUpdateAdapter,
)
from app.services.workspaces import ensure_personal_workspace


async def _listing_context(db_session, email: str):
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
        title="旧标题",
    )
    db_session.add(product)
    await db_session.flush()
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="shopify",
        title="旧标题",
        description="旧描述",
        content_hash="a" * 64,
        status="published",
        compliance_status="pass",
    )
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="listing-update.myshopify.com",
        shop_domain="listing-update.myshopify.com",
        access_token=encrypt_value("shpat_listing"),
    )
    db_session.add_all([listing, channel])
    await db_session.flush()
    publication = Publication(
        user_id=user.id,
        listing_id=listing.id,
        platform="shopify",
        channel_id=str(channel.id),
        status="completed",
        external_product_id="gid://shopify/Product/600",
    )
    db_session.add(publication)
    await db_session.commit()
    return user, workspace, product, listing, channel


def _transport(state: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/products/600.json"):
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "product": {
                            "id": 600,
                            "title": state["title"],
                            "body_html": state["description"],
                            "status": state["status"],
                        }
                    },
                )
            if request.method == "PUT":
                body = json.loads(request.content)["product"]
                state["put_count"] += 1
                state["title"] = body.get("title", state["title"])
                state["description"] = body.get(
                    "body_html",
                    state["description"],
                )
                state["status"] = body.get("status", state["status"])
                return httpx.Response(
                    200,
                    json={
                        "product": {
                            "id": 600,
                            "title": state["title"],
                            "body_html": state["description"],
                            "status": state["status"],
                        }
                    },
                )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_listing_update_preflights_executes_and_syncs_local_draft(
    db_session,
):
    user, workspace, _product, listing, channel = await _listing_context(
        db_session,
        "listing-update@example.com",
    )
    state = {
        "title": "旧标题",
        "description": "旧描述",
        "status": "active",
        "put_count": 0,
    }
    adapter = ShopifyListingUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(state),
    )
    input_data = {
        "channel_id": str(channel.id),
        "title": "夏季旅行收纳包",
        "description": "轻量防泼水，适合短途旅行。",
    }

    snapshot = await adapter.preflight(
        action_id="listings.update",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="listings.update",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="listing-update-1",
    )
    verification = await adapter.verify(
        action_id="listings.update",
        target_id=str(listing.id),
        execution=execution,
    )

    assert snapshot["before"]["title"] == "旧标题"
    assert state["title"] == "夏季旅行收纳包"
    assert state["put_count"] == 1
    assert verification.matched is True
    assert listing.title == "夏季旅行收纳包"
    assert listing.description == "轻量防泼水，适合短途旅行。"
    assert listing.version == 2
    assert listing.status == "published"
    assert listing.compliance_status == "unknown"


@pytest.mark.asyncio
async def test_listing_update_rejects_empty_change_set(db_session):
    user, workspace, _product, listing, channel = await _listing_context(
        db_session,
        "listing-update-empty@example.com",
    )
    adapter = ShopifyListingUpdateAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        transport=_transport(
            {
                "title": "旧标题",
                "description": "旧描述",
                "status": "active",
                "put_count": 0,
            }
        ),
    )

    with pytest.raises(ValueError, match="至少修改"):
        await adapter.preflight(
            action_id="listings.update",
            target_id=str(listing.id),
            input_data={"channel_id": str(channel.id)},
        )


@pytest.mark.asyncio
async def test_dispatcher_routes_listing_update(db_session):
    user, workspace, _product, listing, _channel = await _listing_context(
        db_session,
        "listing-update-dispatch@example.com",
    )
    from app.models.action_run import ActionRun

    run = ActionRun(
        workspace_id=workspace.id,
        work_item_id=uuid4(),
        action_id="listings.update",
        platform="shopify",
        target_type="listings",
        target_id=str(listing.id),
        input_json="{}",
        status="queued",
        risk_level="high",
        autonomy_level="confirm",
        idempotency_key="listing-update-dispatch-1",
    )

    adapter = await resolve_action_adapter(db_session, run)

    assert isinstance(adapter, ShopifyListingUpdateAdapter)
