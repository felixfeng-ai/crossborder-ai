"""Shopify 库存与本地 SKU 对账信号测试。"""

from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_signal import AgentSignal, IntegrationCursor
from app.models.agent_work import WorkItem
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.shopify_inventory_signal_sync import (
    ShopifyRateLimitError,
    sync_shopify_inventory_signals,
)
from app.services.workspaces import ensure_personal_workspace


async def _inventory_context(db_session, email: str, local_stock: int = 12):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="inventory-store.myshopify.com",
        shop_domain="inventory-store.myshopify.com",
        access_token=encrypt_value("shpat_inventory"),
        is_active=True,
    )
    product = Product(
        user_id=user.id,
        url=f"https://example.com/{user.id}",
        title="Inventory Product",
    )
    db_session.add_all([channel, product])
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        product_id=product.id,
        sku="SKU-INV-1",
        price=19.9,
        stock_quantity=local_stock,
        is_active=True,
    )
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(channel)
    await db_session.refresh(variant)
    return user, workspace, channel, variant


def _transport(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/products.json"):
            if state.get("status_code") == 429:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "30"},
                    json={"errors": "throttled"},
                )
            return httpx.Response(
                200,
                json={
                    "products": [
                        {
                            "id": 501,
                            "title": "Inventory Product",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "variants": [
                                {
                                    "id": 601,
                                    "sku": "SKU-INV-1",
                                    "inventory_quantity": state["remote_stock"],
                                }
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_remote_zero_stock_creates_out_of_stock_signal(db_session):
    _user, workspace, channel, variant = await _inventory_context(
        db_session,
        "inventory-zero@example.com",
        local_stock=12,
    )
    result = await sync_shopify_inventory_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport({"remote_stock": 0}),
    )
    await db_session.commit()
    signal = (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one()
    await db_session.refresh(variant)

    assert result["signals_created"] == 1
    assert signal.signal_type == "inventory_out_of_stock"
    assert variant.stock_quantity == 12  # 不自动覆盖本地库存


@pytest.mark.asyncio
async def test_matching_healthy_stock_resolves_previous_signal(db_session):
    _user, workspace, channel, variant = await _inventory_context(
        db_session,
        "inventory-resolve@example.com",
        local_stock=8,
    )
    await sync_shopify_inventory_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport({"remote_stock": 0}),
    )
    await db_session.commit()
    result = await sync_shopify_inventory_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport({"remote_stock": 8}),
    )
    await db_session.commit()
    signal = (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one()

    assert result["signals_resolved"] == 1
    assert signal.status == "resolved"
    assert variant.stock_quantity == 8


@pytest.mark.asyncio
async def test_stock_mismatch_creates_conflict_without_auto_overwrite(db_session):
    _user, workspace, channel, variant = await _inventory_context(
        db_session,
        "inventory-conflict@example.com",
        local_stock=8,
    )
    result = await sync_shopify_inventory_signals(
        db_session,
        workspace_id=workspace.id,
        channel=channel,
        transport=_transport({"remote_stock": 2}),
    )
    await db_session.commit()
    signal = (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    await db_session.refresh(variant)

    assert result["signals_created"] == 1
    assert signal.signal_type == "inventory_conflict"
    assert work.requires_action == "confirm"
    assert variant.stock_quantity == 8


@pytest.mark.asyncio
async def test_inventory_rate_limit_keeps_cursor_untouched(db_session):
    _user, workspace, channel, _variant = await _inventory_context(
        db_session,
        "inventory-rate@example.com",
    )
    with pytest.raises(ShopifyRateLimitError):
        await sync_shopify_inventory_signals(
            db_session,
            workspace_id=workspace.id,
            channel=channel,
            transport=_transport(
                {"remote_stock": 0, "status_code": 429}
            ),
        )
    assert (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id
            )
        )
    ).scalar_one_or_none() is None
