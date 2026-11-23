"""Agent 待确认动作转工作项测试。"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.agent_work import WorkItem
from app.models.action_run import ActionRun
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.image_asset import ImageAsset
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services.work_items import create_work_items_from_agent_result
from app.services.workspaces import ensure_personal_workspace


async def _workspace(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    return user, workspace


@pytest.mark.asyncio
async def test_agent_pending_image_action_creates_one_confirmation_work(
    db_session,
):
    user, workspace = await _workspace(
        db_session,
        "agent-pending-image@example.com",
    )
    task_id = uuid4()
    result = {
        "summary": "图片生成方案已准备",
        "steps": [
            {
                "action": "generate_image_asset",
                "status": "success",
                "summary": "预计消耗 8 积分",
                "data": {
                    "requires_confirmation": True,
                    "pending_action": {
                        "action": "generate_image_asset",
                        "params": {
                            "prompt": "白色背景商品图",
                            "num_outputs": 2,
                        },
                        "estimated_credits": 8,
                    },
                },
            }
        ],
    }

    first = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=task_id,
        result=result,
    )
    second = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=task_id,
        result=result,
    )
    await db_session.commit()

    count = (
        await db_session.execute(
            select(func.count()).select_from(WorkItem).where(
                WorkItem.workspace_id == workspace.id,
                WorkItem.source_type == "agent_pending_action",
            )
        )
    ).scalar_one()
    item = first[0]
    assert len(first) == 1
    assert len(second) == 1
    assert second[0].id == item.id
    assert count == 1
    assert item.status == "waiting_user"
    assert item.requires_action == "confirm"
    assert "图片" in item.title
    assert "8" in item.summary


@pytest.mark.asyncio
async def test_registered_pending_action_is_linked_to_action_run(db_session):
    user, workspace = await _workspace(
        db_session,
        "agent-pending-fulfillment@example.com",
    )
    task_id = uuid4()
    result = {
        "summary": "订单履约方案已准备",
        "steps": [
            {
                "action": "orders.fulfill",
                "data": {
                    "requires_confirmation": True,
                    "pending_action": {
                        "action": "orders.fulfill",
                        "params": {
                            "order_id": "9001",
                            "channel_id": str(uuid4()),
                            "tracking_number": "TRACK-1",
                            "tracking_company": "UPS",
                        },
                    },
                },
            }
        ],
    }

    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=task_id,
        result=result,
    )
    await db_session.commit()
    action_run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace.id,
                ActionRun.work_item_id == items[0].id,
            )
        )
    ).scalar_one()

    assert action_run.action_id == "orders.fulfill"
    assert action_run.target_id == "9001"
    assert action_run.status == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_agent_price_update_creates_variant_confirmation(db_session):
    user, workspace = await _workspace(
        db_session,
        "agent-pending-price@example.com",
    )
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        url="https://example.com/price-product",
        title="旅行收纳包",
    )
    db_session.add(product)
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        sku="SKU-PRICE",
        price=20.0,
    )
    db_session.add(variant)
    await db_session.flush()
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="shopify",
        title="旅行收纳包",
        content_hash="b" * 64,
        status="published",
    )
    db_session.add(listing)
    await db_session.flush()
    db_session.add(
        Publication(
            user_id=user.id,
            listing_id=listing.id,
            platform="shopify",
            channel_id=str(uuid4()),
            status="completed",
            external_product_id="gid://shopify/Product/888",
        )
    )
    await db_session.commit()
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )

    result = await orchestrator._do_update_shopify_price(
        {
            "variant_id": str(variant.id),
            "price": "24.99",
        }
    )
    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=uuid4(),
        result=result,
    )
    await db_session.commit()
    action_run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.work_item_id == items[0].id,
            )
        )
    ).scalar_one()

    assert result["data"]["pending_action"]["action"] == "pricing.update"
    assert action_run.target_id == str(variant.id)
    assert action_run.action_id == "pricing.update"


@pytest.mark.asyncio
async def test_agent_inventory_update_requires_owned_variant(db_session):
    user, workspace = await _workspace(
        db_session,
        "agent-pending-stock@example.com",
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )

    result = await orchestrator._do_update_shopify_inventory(
        {
            "variant_id": str(uuid4()),
            "stock_quantity": 12,
        }
    )

    assert result["status"] == "failed"
    assert "SKU" in result["error"]


@pytest.mark.asyncio
async def test_agent_listing_update_creates_listing_confirmation(db_session):
    user, workspace = await _workspace(
        db_session,
        "agent-pending-listing@example.com",
    )
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        url="https://example.com/listing-product",
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
        content_hash="c" * 64,
        status="published",
    )
    db_session.add(listing)
    await db_session.flush()
    db_session.add(
        Publication(
            user_id=user.id,
            listing_id=listing.id,
            platform="shopify",
            channel_id=str(uuid4()),
            status="completed",
            external_product_id="gid://shopify/Product/999",
        )
    )
    await db_session.commit()
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )

    result = await orchestrator._do_update_shopify_listing(
        {
            "listing_id": str(listing.id),
            "title": "新标题",
            "status": "draft",
        }
    )
    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=uuid4(),
        result=result,
    )
    await db_session.commit()
    action_run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.work_item_id == items[0].id,
            )
        )
    ).scalar_one()

    assert result["data"]["pending_action"]["action"] == "listings.update"
    assert action_run.target_id == str(listing.id)


@pytest.mark.asyncio
async def test_agent_order_cancel_creates_high_risk_confirmation(db_session):
    user, workspace = await _workspace(
        db_session,
        "agent-pending-cancel@example.com",
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="cancel-agent.myshopify.com",
        shop_domain="cancel-agent.myshopify.com",
        access_token="encrypted",
    )
    db_session.add(channel)
    await db_session.commit()

    result = await orchestrator._do_cancel_shopify_order(
        {
            "order_id": "9100",
            "channel_id": str(channel.id),
            "reason": "customer",
            "restock": True,
            "refund": False,
            "notify_customer": True,
        }
    )
    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=uuid4(),
        result=result,
    )
    await db_session.commit()
    action_run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.work_item_id == items[0].id,
            )
        )
    ).scalar_one()

    assert result["data"]["pending_action"]["action"] == "orders.cancel"
    assert action_run.target_id == "9100"


@pytest.mark.asyncio
async def test_agent_listing_media_creates_attach_confirmation(
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user, workspace = await _workspace(
        db_session,
        "agent-pending-media@example.com",
    )
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        url="https://example.com/media-product",
        title="旅行收纳包",
    )
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="shopify",
        title="旅行收纳包",
        content_hash="e" * 64,
        status="published",
    )
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=workspace.id,
        name="scene",
        kind="generated",
        storage_key="media/scene.png",
        content_type="image/png",
        width=10,
        height=10,
        file_size=10,
    )
    target = tmp_path / asset.storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fake-image")
    db_session.add(product)
    await db_session.flush()
    listing.product_id = product.id
    db_session.add_all([listing, asset])
    await db_session.flush()
    db_session.add(
        Publication(
            user_id=user.id,
            listing_id=listing.id,
            platform="shopify",
            channel_id=str(uuid4()),
            status="completed",
            external_product_id="gid://shopify/Product/1000",
        )
    )
    await db_session.commit()
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )

    result = await orchestrator._do_attach_shopify_listing_images(
        {
            "listing_id": str(listing.id),
            "asset_ids": [str(asset.id)],
        }
    )
    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=uuid4(),
        result=result,
    )
    await db_session.commit()
    action_run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.work_item_id == items[0].id,
            )
        )
    ).scalar_one()

    assert result["data"]["pending_action"]["action"] == "listing.media.attach"
    assert action_run.target_id == str(listing.id)
