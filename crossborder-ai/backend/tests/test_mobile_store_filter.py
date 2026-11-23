"""移动端店铺清单和时间线筛选测试。"""

from sqlalchemy import select

import pytest

from app.core.crypto import encrypt_value
from app.models.platform_connection import PlatformConnection
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.work_items import create_work_item
from app.services.workspaces import ensure_personal_workspace
from app.services.notifications import create_notification


@pytest.mark.asyncio
async def test_mobile_commerce_store_filter_and_safe_connection_list(
    client,
    db_session,
):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "mobile-store-filter@example.com",
            "username": "mobile-store-filter",
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(
                User.email == "mobile-store-filter@example.com"
            )
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    shopify = ShopifyChannel(
        user_id=user.id,
        workspace_id=workspace.id,
        shop_name="alpha.myshopify.com",
        shop_domain="alpha.myshopify.com",
        access_token=encrypt_value("shpat-super-secret"),
    )
    amazon = PlatformConnection(
        user_id=user.id,
        platform="amazon",
        account_name="Amazon US",
        external_account_id="A1STORE",
        marketplace_id="ATVPDKIKX0DER",
        credentials=encrypt_value('{"refresh_token":"secret"}'),
        status="active",
    )
    db_session.add_all([shopify, amazon])
    await db_session.flush()

    shop_item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="order_exception",
        source="integration",
        title="Shopify 订单",
        summary="只属于 Shopify 店铺。",
        requires_action="confirm",
        channel_type="shopify",
        channel_id=str(shopify.id),
    )
    amazon_item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="order_exception",
        source="integration",
        title="Amazon 订单",
        summary="只属于 Amazon 店铺。",
        requires_action="confirm",
        channel_type="amazon",
        channel_id=str(amazon.id),
    )
    legacy = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="order_exception",
        source="integration",
        title="历史未归因订单",
        summary="只在全部店铺显示。",
        requires_action="confirm",
    )
    await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        work_item_id=shop_item.id,
        notification_type="needs_action",
        title="Shopify 通知",
        body="只显示在 Shopify 店铺。",
        deep_link=f"/t/{shop_item.id}?workspaceId={workspace.id}",
        dedupe_key="store-filter:shopify",
    )
    await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        work_item_id=amazon_item.id,
        notification_type="needs_action",
        title="Amazon 通知",
        body="只显示在 Amazon 店铺。",
        deep_link=f"/t/{amazon_item.id}?workspaceId={workspace.id}",
        dedupe_key="store-filter:amazon",
    )
    await db_session.commit()

    stores = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/commerce-stores",
        headers=headers,
    )
    filtered = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/timeline",
        headers=headers,
        params={
            "channel_type": "shopify",
            "channel_id": str(shopify.id),
        },
    )
    notifications = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/notifications",
        headers=headers,
        params={
            "channel_type": "shopify",
            "channel_id": str(shopify.id),
        },
    )

    assert stores.status_code == 200
    assert len(stores.json()) == 2
    assert "shpat-super-secret" not in stores.text
    assert "refresh_token" not in stores.text
    assert filtered.status_code == 200
    assert [entry["id"] for entry in filtered.json()["items"]] == [
        str(shop_item.id)
    ]
    assert str(amazon_item.id) not in filtered.text
    assert str(legacy.id) not in filtered.text
    assert notifications.status_code == 200
    assert notifications.json()
    assert all(
        item["work_item_id"] == str(shop_item.id)
        for item in notifications.json()
    )
