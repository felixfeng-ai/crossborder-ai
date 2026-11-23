"""后台动作分发器。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_run import ActionRun
from app.models.workspace import Workspace
from app.services.action_runtime import ActionAdapter, execute_action_run
from app.services.shopify_action_adapter import ShopifyPublishActionAdapter
from app.services.shopify_fulfillment_adapter import (
    ShopifyFulfillmentActionAdapter,
)
from app.services.shopify_refund_adapter import ShopifyRefundActionAdapter
from app.services.shopify_variant_adapter import ShopifyVariantActionAdapter
from app.services.shopify_listing_update_adapter import (
    ShopifyListingUpdateAdapter,
)
from app.services.shopify_order_cancel_adapter import (
    ShopifyOrderCancelActionAdapter,
)
from app.services.shopify_listing_media_adapter import (
    ShopifyListingMediaActionAdapter,
)
from app.services.customer_reply_adapter import CustomerReplyActionAdapter
from app.services.judge_me_review_service import JudgeMeReviewActionAdapter
from app.services.media_action_adapter import MediaGenerationActionAdapter
from app.services.amazon_listing_action_adapter import (
    AmazonListingPublishActionAdapter,
)
from app.services.amazon_fulfillment_adapter import (
    AmazonOrderFulfillmentActionAdapter,
)
from app.services.temu_fulfillment_adapter import (
    TemuOrderFulfillmentActionAdapter,
)
from app.services.temu_listing_publish_adapter import (
    TemuListingPublishActionAdapter,
)
from app.services.temu_inventory_adapter import (
    TemuInventoryUpdateActionAdapter,
)
from app.services.temu_price_adapter import TemuPriceUpdateActionAdapter
from app.services.amazon_offer_adapter import AmazonOfferUpdateAdapter
from app.services.amazon_listing_content_adapter import (
    AmazonListingContentUpdateAdapter,
)
from app.services.amazon_listing_media_adapter import (
    AmazonListingMediaAttachAdapter,
)
from app.services.amazon_listing_asset_media_adapter import (
    AmazonListingAssetMediaAdapter,
)


async def resolve_action_adapter(
    db: AsyncSession,
    run: ActionRun,
) -> ActionAdapter | None:
    """按动作能力选择平台适配器，未接入平台保持排队而不是伪成功。"""

    if run.action_id not in {
        "listings.publish",
        "orders.fulfill",
        "refunds.create",
        "messages.reply",
        "orders.delay_notice",
        "pricing.update",
        "inventory.update",
        "listings.update",
        "orders.cancel",
        "listing.media.attach",
        "reviews.reply",
        "media.generate_image",
        "media.generate_video",
        "amazon.listings.publish",
        "amazon.orders.fulfill",
        "amazon.inventory.update",
        "amazon.pricing.update",
        "amazon.listings.update",
        "amazon.listing.media.attach",
        "amazon.listing.media.attach_assets",
        "temu.orders.fulfill",
        "temu.listings.submit",
        "temu.inventory.update",
        "temu.pricing.submit",
    }:
        return None

    user_id = run.confirmed_by_user_id
    if user_id is None:
        workspace = await db.get(Workspace, run.workspace_id)
        if workspace is None:
            return None
        user_id = workspace.owner_user_id
    if run.action_id == "listings.publish":
        return ShopifyPublishActionAdapter(db, user_id=user_id)
    if run.action_id == "orders.fulfill":
        return ShopifyFulfillmentActionAdapter(db, user_id=user_id)
    if run.action_id == "refunds.create":
        return ShopifyRefundActionAdapter(db, user_id=user_id)
    if run.action_id in {"pricing.update", "inventory.update"}:
        return ShopifyVariantActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "listings.update":
        return ShopifyListingUpdateAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "orders.cancel":
        return ShopifyOrderCancelActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "listing.media.attach":
        return ShopifyListingMediaActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "reviews.reply":
        return JudgeMeReviewActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id in {"media.generate_image", "media.generate_video"}:
        return MediaGenerationActionAdapter(db, user_id=user_id)
    if run.action_id == "amazon.listings.publish":
        return AmazonListingPublishActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "amazon.orders.fulfill":
        return AmazonOrderFulfillmentActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "temu.orders.fulfill":
        return TemuOrderFulfillmentActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "temu.listings.submit":
        return TemuListingPublishActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "temu.inventory.update":
        return TemuInventoryUpdateActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "temu.pricing.submit":
        return TemuPriceUpdateActionAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id in {
        "amazon.inventory.update",
        "amazon.pricing.update",
    }:
        return AmazonOfferUpdateAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "amazon.listings.update":
        return AmazonListingContentUpdateAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "amazon.listing.media.attach":
        return AmazonListingMediaAttachAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    if run.action_id == "amazon.listing.media.attach_assets":
        return AmazonListingAssetMediaAdapter(
            db,
            user_id=user_id,
            workspace_id=run.workspace_id,
        )
    return CustomerReplyActionAdapter(
        db,
        workspace_id=run.workspace_id,
        user_id=user_id,
    )


async def dispatch_queued_action_runs(
    db: AsyncSession,
    *,
    limit: int = 5,
) -> int:
    """执行当前已接入适配器的排队动作。

    每个动作独立提交，某个 Shopify 店铺失败不会回滚其他工作区已经完成的动作。
    """

    runs = (
        await db.execute(
            select(ActionRun)
            .where(ActionRun.status == "queued")
            .order_by(ActionRun.created_at, ActionRun.id)
            .limit(max(1, limit))
        )
    ).scalars().all()

    executed = 0
    for run in runs:
        adapter = await resolve_action_adapter(db, run)
        if adapter is None:
            continue
        try:
            executed_run = await execute_action_run(
                db,
                workspace_id=run.workspace_id,
                action_run_id=run.id,
                adapter=adapter,
            )
            await db.commit()
            if executed_run.status == "succeeded":
                executed += 1
        except Exception:
            # 运行时已经把可恢复失败写入动作记录，保留状态供用户重试。
            await db.commit()
    return executed
