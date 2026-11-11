"""完整整店巡检：基础资料、Listing、素材、SKU、发布与运营预警。"""

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing_draft import ListingDraft
from app.models.operation_alert import OperationAlert
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.store_check_log import StoreCheckLog
from app.models.user import User


STORE_CHECK_SCOPES = [
    "basic",
    "listing",
    "media",
    "sku",
    "publication",
    "operations",
]

SEVERITY_ORDER = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "critical": 3,
}


def _issue(
    code: str,
    label: str,
    *,
    severity: str,
    action_href: str,
) -> dict[str, str]:
    return {
        "code": code,
        "label": label,
        "severity": severity,
        "action_href": action_href,
    }


def _max_severity(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "info"
    return max(
        (str(item.get("severity") or "info") for item in issues),
        key=lambda item: SEVERITY_ORDER.get(item, 0),
    )


async def run_store_check(
    db: AsyncSession,
    user: User,
    *,
    persist_log: bool = True,
) -> dict[str, Any]:
    """执行完整整店巡检并写入可展开的历史记录。"""
    products = (
        await db.execute(
            select(Product)
            .where(Product.user_id == user.id)
            .order_by(desc(Product.updated_at))
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
            select(ProductVariant).where(ProductVariant.user_id == user.id)
        )
    ).scalars().all()
    publications = (
        await db.execute(
            select(Publication).where(
                Publication.user_id == user.id,
                Publication.status == "completed",
            )
        )
    ).scalars().all()
    alerts = (
        await db.execute(
            select(OperationAlert).where(
                OperationAlert.user_id == user.id,
                OperationAlert.status == "open",
            )
        )
    ).scalars().all()

    latest_listing_by_product: dict = {}
    for listing in listings:
        latest_listing_by_product.setdefault(listing.product_id, listing)
    variants_by_product: dict = {}
    for variant in variants:
        variants_by_product.setdefault(variant.product_id, []).append(variant)
    published_listing_ids = {
        item.listing_id for item in publications if item.listing_id is not None
    }
    alerts_by_product: dict = {}
    for alert in alerts:
        if alert.product_id is not None:
            alerts_by_product.setdefault(alert.product_id, []).append(alert)

    issues: list[dict[str, Any]] = []
    healthy = 0
    for product in products:
        product_issues: list[dict[str, str]] = []
        product_href = f"/app/products/{product.id}"
        if not product.title:
            product_issues.append(
                _issue(
                    "missing_title",
                    "缺标题",
                    severity="warning",
                    action_href=product_href,
                )
            )
        if not product.price:
            product_issues.append(
                _issue(
                    "missing_price",
                    "缺供货参考价",
                    severity="warning",
                    action_href=product_href,
                )
            )
        if not product.url:
            product_issues.append(
                _issue(
                    "missing_url",
                    "缺商品链接",
                    severity="warning",
                    action_href=product_href,
                )
            )

        latest_listing = latest_listing_by_product.get(product.id)
        if latest_listing is None:
            product_issues.append(
                _issue(
                    "missing_listing",
                    "未生成 Listing",
                    severity="warning",
                    action_href=f"/app/content?product={product.id}&platform=shopify",
                )
            )
        elif (
            latest_listing.compliance_status == "block"
            or latest_listing.status == "blocked"
        ):
            product_issues.append(
                _issue(
                    "listing_blocked",
                    "Listing 合规阻断",
                    severity="error",
                    action_href=(
                        f"/app/products/{product.id}?listing={latest_listing.id}"
                    ),
                )
            )
        elif (
            latest_listing.status != "ready"
            or latest_listing.compliance_status != "pass"
        ):
            product_issues.append(
                _issue(
                    "listing_needs_review",
                    "Listing 待复审",
                    severity="warning",
                    action_href=(
                        f"/app/products/{product.id}?listing={latest_listing.id}"
                    ),
                )
            )

        if not product.main_image_url:
            product_issues.append(
                _issue(
                    "missing_main_image",
                    "缺商品主图",
                    severity="warning",
                    action_href="/app/images",
                )
            )

        active_variants = [
            item for item in variants_by_product.get(product.id, []) if item.is_active
        ]
        if not active_variants:
            product_issues.append(
                _issue(
                    "missing_active_sku",
                    "未配置启用 SKU",
                    severity="warning",
                    action_href="/app/catalog",
                )
            )
        else:
            missing_price = [
                item for item in active_variants
                if item.price is None or item.price <= 0
            ]
            if missing_price:
                product_issues.append(
                    _issue(
                        "sku_missing_price",
                        f"{len(missing_price)} 个 SKU 缺销售价",
                        severity="warning",
                        action_href="/app/catalog",
                    )
                )
            out_of_stock = [
                item for item in active_variants if (item.stock_quantity or 0) <= 0
            ]
            if out_of_stock:
                product_issues.append(
                    _issue(
                        "sku_out_of_stock",
                        f"{len(out_of_stock)} 个 SKU 缺货",
                        severity="warning",
                        action_href="/app/operations",
                    )
                )

        if (
            latest_listing is not None
            and latest_listing.status == "ready"
            and latest_listing.compliance_status == "pass"
            and latest_listing.id not in published_listing_ids
        ):
            product_issues.append(
                _issue(
                    "not_published",
                    "尚未发布渠道",
                    severity="info",
                    action_href=(
                        f"/app/content?product={product.id}&platform=shopify"
                    ),
                )
            )

        product_alerts = alerts_by_product.get(product.id, [])
        if product_alerts:
            product_issues.append(
                _issue(
                    "open_operation_alert",
                    f"{len(product_alerts)} 条运营预警待处理",
                    severity=max(
                        (item.severity for item in product_alerts),
                        key=lambda item: SEVERITY_ORDER.get(item, 0),
                    ),
                    action_href="/app/operations",
                )
            )

        if product_issues:
            issues.append(
                {
                    "id": str(product.id),
                    "title": product.title or "未命名商品",
                    "severity": _max_severity(product_issues),
                    "action_href": product_href,
                    "issues": product_issues,
                }
            )
        else:
            healthy += 1

    total = len(products)
    issue_count = len(issues)
    result = {
        "total": total,
        "healthy": healthy,
        "issue_count": issue_count,
        "issues": issues,
        "checked_scopes": list(STORE_CHECK_SCOPES),
        "summary": (
            f"巡检完成：共 {total} 个商品，"
            f"{issue_count} 个有问题，{healthy} 个正常"
        ),
    }
    if persist_log:
        log = StoreCheckLog(
            user_id=user.id,
            total=total,
            healthy=healthy,
            issue_count=issue_count,
            issues_json=json.dumps(issues, ensure_ascii=False) if issues else None,
        )
        db.add(log)
        await db.flush()
        result["log_id"] = str(log.id)
    return result
