"""Amazon 移动 Agent Listing 发布动作测试。"""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_work import WorkItem
from app.models.action_run import ActionRun
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.action_runtime import plan_action_run
from app.services.workspaces import ensure_personal_workspace
from app.services.work_items import create_work_items_from_agent_result


class FakeAmazonPublishService:
    calls = []

    async def submit_listing(self, **kwargs):
        self.calls.append(("submit", kwargs))
        return {
            "sku": kwargs["sku"],
            "status": "ACCEPTED",
            "submissionId": "amazon-submission-1",
            "issues": [],
        }

    async def get_listing(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {
            "sku": kwargs["sku"],
            "summaries": [
                {
                    "marketplaceId": kwargs["marketplace_id"],
                    "asin": "B012345678",
                    "productType": "LUGGAGE",
                    "status": ["BUYABLE", "DISCOVERABLE"],
                }
            ],
            "issues": [],
        }


async def _amazon_context(db_session, email: str):
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
        url="https://detail.1688.com/offer/amazon-action.html",
        title="Travel Mug",
        brand_name="Veya",
        description="Insulated travel mug",
    )
    db_session.add(product)
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        sku="AMZ-MUG-1",
        price=29.99,
        stock_quantity=12,
        is_active=True,
    )
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        product_id=product.id,
        platform="amazon",
        language="en",
        title="Veya Insulated Travel Mug",
        description="Keeps drinks hot for hours.",
        bullet_points=json.dumps(
            ["Leak resistant", "Easy to clean"],
            ensure_ascii=False,
        ),
        content_hash="hash-amazon-action",
        compliance_status="passed",
        compliance_violations="[]",
        version=1,
    )
    connection = PlatformConnection(
        user_id=user.id,
        platform="amazon",
        account_name="Amazon US",
        external_account_id="A2SELLER",
        marketplace_id="ATVPDKIKX0DER",
        credentials=encrypt_value(
            json.dumps({"refresh_token": "Atzr|refresh"})
        ),
        status="active",
    )
    db_session.add_all([variant, listing, connection])
    await db_session.flush()
    item = WorkItem(
        workspace_id=workspace.id,
        kind="agent_action",
        source="agent",
        title="发布 Amazon Listing",
        summary="等待确认",
        status="waiting_user",
        requires_action="confirm",
    )
    db_session.add(item)
    await db_session.commit()
    for obj in (workspace, product, variant, listing, connection, item):
        await db_session.refresh(obj)
    return user, workspace, product, variant, listing, connection, item


@pytest.mark.asyncio
async def test_amazon_agent_action_preflight_builds_payload(db_session):
    from app.services.amazon_listing_action_adapter import (
        AmazonListingPublishActionAdapter,
    )

    user, workspace, _product, variant, listing, _connection, _item = (
        await _amazon_context(
            db_session,
            "amazon-action-preflight@example.com",
        )
    )
    service = FakeAmazonPublishService()
    adapter = AmazonListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )

    snapshot = await adapter.preflight(
        action_id="amazon.listings.publish",
        target_id=str(listing.id),
        input_data={
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "product_type": "LUGGAGE",
            "marketplace_id": "ATVPDKIKX0DER",
        },
    )

    assert snapshot["sku"] == "AMZ-MUG-1"
    assert snapshot["listing_version"] == 1
    assert snapshot["preview_status"] == "ACCEPTED"
    assert "Atzr|refresh" not in json.dumps(snapshot)
    kind, call = service.calls[0]
    assert kind == "submit"
    assert call["preview"] is True
    assert call["payload"]["productType"] == "LUGGAGE"
    assert call["payload"]["attributes"]["purchasable_offer"][0][
        "our_price"
    ][0]["schedule"][0]["value_with_tax"] == 29.99


@pytest.mark.asyncio
async def test_amazon_agent_action_executes_and_reads_back_listing(
    db_session,
):
    from app.services.amazon_listing_action_adapter import (
        AmazonListingPublishActionAdapter,
    )

    user, workspace, _product, variant, listing, _connection, _item = (
        await _amazon_context(
            db_session,
            "amazon-action-execute@example.com",
        )
    )
    service = FakeAmazonPublishService()
    adapter = AmazonListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=service,
    )
    input_data = {
        "listing_id": str(listing.id),
        "variant_id": str(variant.id),
        "product_type": "LUGGAGE",
        "marketplace_id": "ATVPDKIKX0DER",
    }

    execution = await adapter.execute(
        action_id="amazon.listings.publish",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="amazon-action-1",
    )
    verification = await adapter.verify(
        action_id="amazon.listings.publish",
        target_id=str(listing.id),
        execution=execution,
    )

    assert execution.external_id == "amazon-submission-1"
    assert verification.matched is True
    assert verification.snapshot["asin"] == "B012345678"
    assert verification.snapshot["sku"] == "AMZ-MUG-1"
    assert service.calls[-1][0] == "get"


@pytest.mark.asyncio
async def test_amazon_action_uses_work_item_runtime(db_session, monkeypatch):
    from app.services import action_dispatcher
    from app.services.amazon_listing_action_adapter import (
        AmazonListingPublishActionAdapter,
    )

    user, workspace, _product, variant, listing, _connection, item = (
        await _amazon_context(
            db_session,
            "amazon-action-runtime@example.com",
        )
    )
    service = FakeAmazonPublishService()

    def fake_adapter(db, *, user_id, workspace_id):
        return AmazonListingPublishActionAdapter(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            service=service,
        )

    monkeypatch.setattr(
        action_dispatcher,
        "AmazonListingPublishActionAdapter",
        fake_adapter,
    )
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="amazon.listings.publish",
        platform="amazon",
        target_type="product",
        target_id=str(listing.id),
        input_data={
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "product_type": "LUGGAGE",
            "marketplace_id": "ATVPDKIKX0DER",
        },
        idempotency_key="amazon-runtime-1",
        autonomy_level="auto",
    )
    await db_session.commit()

    executed = await action_dispatcher.dispatch_queued_action_runs(
        db_session,
        limit=1,
    )
    await db_session.refresh(run)

    assert run.action_id == "amazon.listings.publish"
    assert run.platform == "amazon"
    assert executed == 1
    assert run.status == "succeeded"
    assert run.external_id == "amazon-submission-1"


@pytest.mark.asyncio
async def test_agent_prepares_amazon_publish_action_without_submitting(
    db_session,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, _product, variant, listing, _connection, _item = (
        await _amazon_context(
            db_session,
            "amazon-agent-pending@example.com",
        )
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )

    result = await orchestrator._execute_step(
        "publish_to_amazon",
        {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": "ATVPDKIKX0DER",
            "product_type": "LUGGAGE",
        },
    )

    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "amazon.listings.publish"
    assert pending["params"]["listing_id"] == str(listing.id)
    assert pending["params"]["variant_id"] == str(variant.id)
    assert pending["params"]["marketplace_id"] == "ATVPDKIKX0DER"

    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=uuid4(),
        result={"steps": [result]},
    )
    await db_session.commit()
    run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.work_item_id == items[0].id
            )
        )
    ).scalar_one()
    assert run.action_id == "amazon.listings.publish"
    assert run.platform == "amazon"
    assert run.target_id == str(listing.id)


@pytest.mark.asyncio
async def test_platform_capabilities_expose_agent_action_boundaries(client):
    response = await client.get("/api/v1/platforms/capabilities")

    assert response.status_code == 200
    platforms = response.json()["platforms"]
    assert "amazon.listings.publish" in platforms["amazon"]["agent_actions"]
    assert platforms["temu"]["auth_supported"] is True
    assert platforms["temu"]["publish_supported"] is True
    assert "temu.listings.submit" in platforms["temu"]["agent_actions"]
    assert "temu.orders.fulfill" in platforms["temu"]["agent_actions"]
    assert "temu.inventory.update" in platforms["temu"]["agent_actions"]
    assert "temu.pricing.submit" in platforms["temu"]["agent_actions"]
    assert "temu.listings.status" in platforms["temu"]["read_actions"]
    assert "listings.publish" in platforms["shopify"]["agent_actions"]
