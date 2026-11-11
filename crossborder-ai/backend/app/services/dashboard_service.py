"""仪表盘真实经营链路与待办聚合。"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_generation_task import ImageGenerationTask
from app.models.listing_draft import ListingDraft
from app.models.marketing_video import MarketingVideoProject
from app.models.operation_alert import OperationAlert
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask


STAGE_LABELS = {
    "product": "来源商品",
    "listing": "AI Listing",
    "media": "图片素材",
    "sku": "SKU / 库存",
    "channel": "渠道发布",
}


def _build_pipeline(
    product: Optional[Product],
    listings: list[ListingDraft],
    variants: list[ProductVariant],
    publications: list[Publication],
) -> dict:
    if product is None:
        return {
            "product": None,
            "stages": [
                {
                    "id": stage_id,
                    "label": label,
                    "status": "pending",
                    "detail": "待开始",
                    "href": "",
                }
                for stage_id, label in STAGE_LABELS.items()
            ],
            "next_action": {
                "stage": "product",
                "label": "录入第一个商品",
                "href": "/app/products",
            },
            "progress": {"completed": 0, "total": 5},
        }

    latest_listing = listings[0] if listings else None
    active_variants = [item for item in variants if item.is_active]
    sellable_variants = [
        item for item in active_variants if item.price is not None and item.price > 0
    ]
    missing_price_count = len(active_variants) - len(sellable_variants)
    completed_publication = next(
        (
            item
            for item in publications
            if latest_listing is not None
            and item.listing_id == latest_listing.id
            and item.status == "completed"
        ),
        None,
    )

    listing_status = "pending"
    listing_detail = "待生成"
    if latest_listing is not None:
        if latest_listing.compliance_status == "block" or latest_listing.status == "blocked":
            listing_status = "blocked"
            listing_detail = f"v{latest_listing.version} 合规阻断"
        elif latest_listing.status == "ready" and latest_listing.compliance_status == "pass":
            listing_status = "completed"
            listing_detail = f"v{latest_listing.version} 合规通过"
        else:
            listing_status = "current"
            listing_detail = f"v{latest_listing.version} 待复审"

    media_status = "completed" if product.main_image_url else "pending"
    media_detail = "主图已就绪" if product.main_image_url else "待上传或生成主图"

    if not active_variants:
        sku_status = "pending"
        sku_detail = "待配置启用 SKU"
    elif missing_price_count:
        sku_status = "blocked"
        sku_detail = f"{missing_price_count} 个 SKU 缺销售价"
    elif any((item.stock_quantity or 0) <= 0 for item in active_variants):
        sku_status = "current"
        sku_detail = "存在缺货 SKU"
    else:
        sku_status = "completed"
        sku_detail = f"{len(active_variants)} 个可售 SKU"

    channel_status = "completed" if completed_publication else "pending"
    channel_detail = "已发布 Shopify 草稿" if completed_publication else "待发布"

    base_stages = [
        {
            "id": "product",
            "label": STAGE_LABELS["product"],
            "status": "completed",
            "detail": "已录入",
            "href": f"/app/products/{product.id}",
        },
        {
            "id": "listing",
            "label": STAGE_LABELS["listing"],
            "status": listing_status,
            "detail": listing_detail,
            "href": (
                f"/app/products/{product.id}?listing={latest_listing.id}"
                if latest_listing
                else f"/app/content?product={product.id}&platform=shopify"
            ),
        },
        {
            "id": "media",
            "label": STAGE_LABELS["media"],
            "status": media_status,
            "detail": media_detail,
            "href": "/app/images",
        },
        {
            "id": "sku",
            "label": STAGE_LABELS["sku"],
            "status": sku_status,
            "detail": sku_detail,
            "href": "/app/catalog",
        },
        {
            "id": "channel",
            "label": STAGE_LABELS["channel"],
            "status": channel_status,
            "detail": channel_detail,
            "href": (
                "/app/shopify"
                if completed_publication
                else f"/app/content?product={product.id}&platform=shopify"
            ),
        },
    ]

    first_incomplete = next(
        (item for item in base_stages if item["status"] != "completed"),
        None,
    )
    if first_incomplete is not None and first_incomplete["status"] == "pending":
        first_incomplete["status"] = "current"

    completed = sum(1 for item in base_stages if item["status"] == "completed")
    return {
        "product": {
            "id": str(product.id),
            "title": product.title or "未命名商品",
            "price": product.price,
            "main_image_url": product.main_image_url,
            "created_at": str(product.created_at),
            "updated_at": str(product.updated_at),
        },
        "stages": base_stages,
        "next_action": {
            "stage": first_incomplete["id"] if first_incomplete else "complete",
            "label": (
                f"继续处理 {first_incomplete['label']}"
                if first_incomplete
                else "查看已发布商品"
            ),
            "href": first_incomplete["href"] if first_incomplete else "/app/catalog",
        },
        "progress": {"completed": completed, "total": len(base_stages)},
    }


def _recent_operations(
    listings: list[ListingDraft],
    image_tasks: list[ImageGenerationTask],
    video_tasks: list[VideoGenerationTask],
    marketing_projects: list[MarketingVideoProject],
    publications: list[Publication],
) -> list[dict]:
    items: list[dict] = []

    for listing in listings[:4]:
        items.append(
            {
                "id": str(listing.id),
                "kind": "listing",
                "title": f"生成 Listing：{listing.title}",
                "detail": f"{listing.platform} · v{listing.version}",
                "href": f"/app/products/{listing.product_id}?listing={listing.id}",
                "created_at": str(listing.updated_at),
                "tone": "ai",
            }
        )
    for task in image_tasks[:3]:
        items.append(
            {
                "id": str(task.id),
                "kind": "image",
                "title": "生成商品图片",
                "detail": task.prompt[:80],
                "href": "/app/images",
                "created_at": str(task.created_at),
                "tone": "ai",
            }
        )
    for task in video_tasks[:3]:
        items.append(
            {
                "id": str(task.id),
                "kind": "video",
                "title": "生成商品图生视频",
                "detail": f"{task.duration}s · {task.resolution}",
                "href": "/app/videos?tab=single",
                "created_at": str(task.created_at),
                "tone": "success" if task.status == "succeeded" else "neutral",
            }
        )
    for project in marketing_projects[:3]:
        items.append(
            {
                "id": str(project.id),
                "kind": "marketing",
                "title": f"营销成片：{project.title}",
                "detail": project.status,
                "href": f"/app/videos?tab=marketing&project={project.id}",
                "created_at": str(project.created_at),
                "tone": "success" if project.status == "succeeded" else "ai",
            }
        )
    for publication in publications[:3]:
        items.append(
            {
                "id": str(publication.id),
                "kind": "publication",
                "title": "发布 Shopify 草稿",
                "detail": publication.status,
                "href": publication.external_url or "/app/shopify",
                "created_at": str(publication.created_at),
                "tone": "success" if publication.status == "completed" else "danger",
            }
        )
    return sorted(items, key=lambda item: item["created_at"], reverse=True)[:6]


async def build_dashboard_data(db: AsyncSession, user: User) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    products = (
        await db.execute(
            select(Product)
            .where(Product.user_id == user.id)
            .order_by(desc(Product.updated_at), desc(Product.created_at))
        )
    ).scalars().all()
    listings = (
        await db.execute(
            select(ListingDraft)
            .where(ListingDraft.user_id == user.id)
            .order_by(desc(ListingDraft.updated_at))
        )
    ).scalars().all()
    variants = (
        await db.execute(
            select(ProductVariant)
            .where(ProductVariant.user_id == user.id)
            .order_by(desc(ProductVariant.updated_at))
        )
    ).scalars().all()
    publications = (
        await db.execute(
            select(Publication)
            .where(
                Publication.user_id == user.id,
                Publication.platform == "shopify",
            )
            .order_by(desc(Publication.created_at))
        )
    ).scalars().all()
    image_tasks = (
        await db.execute(
            select(ImageGenerationTask)
            .where(ImageGenerationTask.user_id == user.id)
            .order_by(desc(ImageGenerationTask.created_at))
            .limit(6)
        )
    ).scalars().all()
    video_tasks = (
        await db.execute(
            select(VideoGenerationTask)
            .where(VideoGenerationTask.user_id == user.id)
            .order_by(desc(VideoGenerationTask.created_at))
            .limit(6)
        )
    ).scalars().all()
    marketing_projects = (
        await db.execute(
            select(MarketingVideoProject)
            .where(MarketingVideoProject.user_id == user.id)
            .order_by(desc(MarketingVideoProject.created_at))
            .limit(6)
        )
    ).scalars().all()
    open_alerts = (
        await db.execute(
            select(func.count(OperationAlert.id)).where(
                OperationAlert.user_id == user.id,
                OperationAlert.status == "open",
            )
        )
    ).scalar() or 0
    month_products = (
        await db.execute(
            select(func.count(Product.id)).where(
                Product.user_id == user.id,
                Product.created_at >= month_start,
            )
        )
    ).scalar() or 0

    latest_listing_by_product: dict = {}
    for listing in listings:
        latest_listing_by_product.setdefault(listing.product_id, listing)
    variants_by_product: dict = {}
    for variant in variants:
        variants_by_product.setdefault(variant.product_id, []).append(variant)

    content_pending = 0
    media_pending = 0
    sku_risk_products = 0
    pending_products: set = set()
    for product in products:
        latest_listing = latest_listing_by_product.get(product.id)
        content_ready = (
            latest_listing is not None
            and latest_listing.status == "ready"
            and latest_listing.compliance_status == "pass"
        )
        if not content_ready:
            content_pending += 1
            pending_products.add(product.id)
        if not product.main_image_url:
            media_pending += 1
            pending_products.add(product.id)
        product_variants = [
            item for item in variants_by_product.get(product.id, []) if item.is_active
        ]
        sku_risky = (
            not product_variants
            or any(item.price is None or item.price <= 0 for item in product_variants)
            or any((item.stock_quantity or 0) <= 0 for item in product_variants)
        )
        if sku_risky:
            sku_risk_products += 1
            pending_products.add(product.id)

    latest_product = products[0] if products else None
    latest_listing = (
        latest_listing_by_product.get(latest_product.id)
        if latest_product is not None
        else None
    )
    pipeline = _build_pipeline(
        latest_product,
        [latest_listing] if latest_listing else [],
        variants_by_product.get(latest_product.id, []) if latest_product else [],
        publications,
    )

    recent = [
        {
            "id": str(product.id),
            "title": product.title or "未命名商品",
            "price": product.price,
            "status": "待补充" if not product.title else "正常",
            "created_at": str(product.created_at),
        }
        for product in products[:5]
    ]
    recent_operations = _recent_operations(
        listings,
        image_tasks,
        video_tasks,
        marketing_projects,
        publications,
    )
    if not recent_operations:
        recent_operations = [
            {
                "id": item["id"],
                "kind": "product",
                "title": f"录入商品：{item['title']}",
                "detail": "来源商品",
                "href": f"/app/products/{item['id']}",
                "created_at": item["created_at"],
                "tone": "neutral",
            }
            for item in recent
        ]

    return {
        "products": {
            "total": len(products),
            "this_month": int(month_products or 0),
            "pending": len(pending_products),
        },
        "pipeline": pipeline,
        "facts": [
            {
                "id": "content",
                "label": "内容待办",
                "value": content_pending,
                "detail": "缺 Listing、合规阻断或待复审",
                "tone": "warning",
                "href": "/app/catalog",
            },
            {
                "id": "media",
                "label": "素材待办",
                "value": media_pending,
                "detail": "缺商品主图",
                "tone": "neutral",
                "href": "/app/images",
            },
            {
                "id": "sku",
                "label": "SKU 风险",
                "value": sku_risk_products,
                "detail": "缺 SKU、售价或库存",
                "tone": "danger" if sku_risk_products else "success",
                "href": "/app/catalog",
            },
            {
                "id": "operations",
                "label": "运营预警",
                "value": int(open_alerts or 0),
                "detail": "待处理补货与经营异常",
                "tone": "danger" if open_alerts else "success",
                "href": "/app/operations",
            },
        ],
        "recent": recent,
        "recent_operations": recent_operations,
        "credits": {"remaining": user.credits},
    }
