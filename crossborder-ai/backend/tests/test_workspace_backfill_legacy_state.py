"""历史无工作区归属数据的可审计回填测试。"""

import pytest
from sqlalchemy import select

from app.models.image_asset import ImageAsset
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.workspace_backfill import SCOPED_MODELS, backfill_workspace_scope
from app.services.workspaces import ensure_personal_workspace


@pytest.mark.asyncio
async def test_backfill_reports_then_restores_legacy_store_and_asset(
    client,
    auth_token,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    personal = await ensure_personal_workspace(db_session, user)
    channel = ShopifyChannel(
        user_id=user.id,
        workspace_id=None,
        shop_name="legacy-admin-shop",
        shop_domain="legacy-admin-shop.myshopify.com",
        access_token="encrypted-token",
        is_active=True,
    )
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=None,
        name="legacy-product.png",
        kind="upload",
        category="product",
        storage_key="legacy/workspace-recovery/product.png",
        content_type="image/png",
        width=800,
        height=800,
        file_size=1024,
    )
    db_session.add_all([channel, asset])
    await db_session.commit()

    tables = ("shopify_channels", "image_assets")
    dry_run = await backfill_workspace_scope(
        db_session,
        dry_run=True,
        tables=tables,
    )
    assert dry_run["shopify_channels"]["would_update"] == 1
    assert dry_run["image_assets"]["would_update"] == 1

    await db_session.refresh(channel)
    await db_session.refresh(asset)
    assert channel.workspace_id is None
    assert asset.workspace_id is None

    applied = await backfill_workspace_scope(
        db_session,
        dry_run=False,
        tables=tables,
    )
    await db_session.commit()
    await db_session.refresh(channel)
    await db_session.refresh(asset)

    assert applied["shopify_channels"]["updated"] == 1
    assert applied["image_assets"]["updated"] == 1
    assert channel.workspace_id == personal.id
    assert asset.workspace_id == personal.id

    complete_audit = await backfill_workspace_scope(
        db_session,
        dry_run=True,
        tables=tuple(SCOPED_MODELS),
    )
    assert set(complete_audit) == set(SCOPED_MODELS)
    assert all(
        result["unresolved"] == 0
        for result in complete_audit.values()
    )
