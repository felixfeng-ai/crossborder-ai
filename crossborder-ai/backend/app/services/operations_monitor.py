"""SKU 级运营快照、补货计算和预警扫描。"""

import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing_draft import ListingDraft
from app.models.monitor_setting import MonitorSetting
from app.models.operation_alert import OperationAlert
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.models.variant_snapshot import VariantSnapshot
from app.services import provider_config
from app.services.scraper import scrape_1688


DEFAULT_SETTINGS = {
    "target_margin_rate": 25.0,
    "low_stock_days": 7,
    "lead_time_days": 14,
    "safety_stock_days": 3,
    "platform_fee_rate": 0.15,
    "shipping_cost": 0.0,
    "cost_increase_alert_rate": 8.0,
}


def calculate_margin(
    selling_price: float | None,
    cost_price: float | None,
    platform_fee_rate: float,
    shipping_cost: float,
) -> dict[str, float | None]:
    if selling_price is None or cost_price is None or selling_price <= 0:
        return {
            "platform_fee": None,
            "net_profit": None,
            "margin_rate": None,
        }
    platform_fee = selling_price * platform_fee_rate
    net_profit = selling_price - platform_fee - cost_price - shipping_cost
    return {
        "platform_fee": round(platform_fee, 2),
        "net_profit": round(net_profit, 2),
        "margin_rate": round(net_profit / selling_price * 100, 2),
    }


def calculate_replenishment(
    stock_quantity: int,
    daily_sales_rate: float,
    lead_time_days: int,
    safety_stock_days: int,
) -> dict[str, Any]:
    if daily_sales_rate <= 0:
        return {
            "days_cover": None,
            "reorder_point": None,
            "suggested_quantity": 0,
            "status": "insufficient_data",
        }

    days_cover = stock_quantity / daily_sales_rate
    reorder_point = math.ceil(
        daily_sales_rate * (lead_time_days + safety_stock_days)
    )
    suggested_quantity = max(0, reorder_point - stock_quantity)
    if stock_quantity <= 0:
        status = "out_of_stock"
    elif stock_quantity <= reorder_point:
        status = "reorder"
    else:
        status = "healthy"
    return {
        "days_cover": round(days_cover, 1),
        "reorder_point": reorder_point,
        "suggested_quantity": suggested_quantity,
        "status": status,
    }


async def get_or_create_settings(db: AsyncSession, user_id) -> MonitorSetting:
    setting = await db.get(MonitorSetting, user_id)
    if setting is None:
        setting = MonitorSetting(user_id=user_id, **DEFAULT_SETTINGS)
        db.add(setting)
        await db.flush()
    return setting


def serialize_settings(setting: MonitorSetting) -> dict[str, Any]:
    return {
        "target_margin_rate": setting.target_margin_rate,
        "low_stock_days": setting.low_stock_days,
        "lead_time_days": setting.lead_time_days,
        "safety_stock_days": setting.safety_stock_days,
        "platform_fee_rate": setting.platform_fee_rate,
        "shipping_cost": setting.shipping_cost,
        "cost_increase_alert_rate": setting.cost_increase_alert_rate,
    }


def serialize_alert(alert: OperationAlert) -> dict[str, Any]:
    try:
        details = json.loads(alert.details_json or "{}")
    except (json.JSONDecodeError, TypeError):
        details = {}
    return {
        "id": str(alert.id),
        "product_id": str(alert.product_id) if alert.product_id else None,
        "variant_id": str(alert.variant_id) if alert.variant_id else None,
        "sku": alert.sku,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "details": details,
        "status": alert.status,
        "created_at": str(alert.created_at),
        "acknowledged_at": str(alert.acknowledged_at) if alert.acknowledged_at else None,
    }


def _alert_key(alert_type: str, variant_id, product_id) -> str:
    return f"{alert_type}:{variant_id or '-'}:{product_id or '-'}"


async def run_monitor_scan(db: AsyncSession, user: User) -> dict[str, Any]:
    """生成最新 SKU 快照、补货计划并同步预警状态。"""
    setting = await get_or_create_settings(db, user.id)

    result = await db.execute(
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.user_id == user.id)
    )
    rows = result.all()

    snapshot_result = await db.execute(
        select(VariantSnapshot)
        .where(VariantSnapshot.user_id == user.id)
        .order_by(desc(VariantSnapshot.captured_at))
    )
    previous_snapshots: dict[Any, VariantSnapshot] = {}
    for snapshot in snapshot_result.scalars().all():
        previous_snapshots.setdefault(snapshot.variant_id, snapshot)

    blocked_result = await db.execute(
        select(ListingDraft).where(
            ListingDraft.user_id == user.id,
            ListingDraft.compliance_status == "block",
        )
    )
    blocked_listings = blocked_result.scalars().all()

    active_result = await db.execute(
        select(OperationAlert).where(
            OperationAlert.user_id == user.id,
            OperationAlert.status.in_(["open", "acknowledged"]),
        )
    )
    active_alerts = {
        _alert_key(alert.alert_type, alert.variant_id, alert.product_id): alert
        for alert in active_result.scalars().all()
    }

    desired: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    low_stock_count = 0
    low_margin_count = 0
    reorder_count = 0
    variants_by_product: dict[Any, list[ProductVariant]] = {}

    for variant, product in rows:
        variants_by_product.setdefault(product.id, []).append(variant)
        cost_price = variant.cost_price if variant.cost_price is not None else product.price
        margin = calculate_margin(
            variant.price,
            cost_price,
            setting.platform_fee_rate,
            setting.shipping_cost,
        )
        replenishment = calculate_replenishment(
            variant.stock_quantity,
            variant.daily_sales_rate,
            setting.lead_time_days,
            setting.safety_stock_days,
        )
        db.add(
            VariantSnapshot(
                user_id=user.id,
                variant_id=variant.id,
                sku=variant.sku,
                selling_price=variant.price,
                cost_price=cost_price,
                stock_quantity=variant.stock_quantity,
                daily_sales_rate=variant.daily_sales_rate,
                margin_rate=margin["margin_rate"],
                captured_at=datetime.now(timezone.utc),
            )
        )

        if variant.price is None:
            key = _alert_key("missing_price", variant.id, product.id)
            desired[key] = {
                "alert_type": "missing_price",
                "variant_id": variant.id,
                "product_id": product.id,
                "sku": variant.sku,
                "severity": "error",
                "title": "SKU 缺售价",
                "message": f"{variant.sku} 未设置售价，无法计算毛利和补货价值。",
                "details": {"stock_quantity": variant.stock_quantity},
            }
        if cost_price is None:
            key = _alert_key("missing_cost", variant.id, product.id)
            desired[key] = {
                "alert_type": "missing_cost",
                "variant_id": variant.id,
                "product_id": product.id,
                "sku": variant.sku,
                "severity": "error",
                "title": "SKU 缺成本",
                "message": f"{variant.sku} 未设置成本，无法判断真实毛利。",
                "details": {},
            }

        if margin["margin_rate"] is not None and margin["margin_rate"] < setting.target_margin_rate:
            low_margin_count += 1
            key = _alert_key("low_margin", variant.id, product.id)
            desired[key] = {
                "alert_type": "low_margin",
                "variant_id": variant.id,
                "product_id": product.id,
                "sku": variant.sku,
                "severity": "warning",
                "title": "SKU 毛利率偏低",
                "message": (
                    f"{variant.sku} 当前毛利率 {margin['margin_rate']:.1f}%，"
                    f"低于目标 {setting.target_margin_rate:.1f}%。"
                ),
                "details": {"margin_rate": margin["margin_rate"]},
            }

        if variant.daily_sales_rate <= 0:
            key = _alert_key("sales_data_missing", variant.id, product.id)
            desired[key] = {
                "alert_type": "sales_data_missing",
                "variant_id": variant.id,
                "product_id": product.id,
                "sku": variant.sku,
                "severity": "info",
                "title": "缺少销量数据",
                "message": f"{variant.sku} 暂无可靠日均销量，无法计算补货点。",
                "details": {"stock_quantity": variant.stock_quantity},
            }
        else:
            days_cover = replenishment["days_cover"]
            if variant.is_active and variant.stock_quantity <= 0:
                key = _alert_key("out_of_stock", variant.id, product.id)
                desired[key] = {
                    "alert_type": "out_of_stock",
                    "variant_id": variant.id,
                    "product_id": product.id,
                    "sku": variant.sku,
                    "severity": "critical",
                    "title": "SKU 已缺货",
                    "message": f"{variant.sku} 当前库存为 0，且仍在售。",
                    "details": {**replenishment},
                }
            elif (
                variant.is_active
                and days_cover is not None
                and days_cover <= setting.low_stock_days
            ):
                low_stock_count += 1
                key = _alert_key("low_stock", variant.id, product.id)
                desired[key] = {
                    "alert_type": "low_stock",
                    "variant_id": variant.id,
                    "product_id": product.id,
                    "sku": variant.sku,
                    "severity": "warning",
                    "title": "SKU 即将缺货",
                    "message": (
                        f"{variant.sku} 库存可覆盖 {days_cover:.1f} 天，"
                        f"低于 {setting.low_stock_days} 天安全线。"
                    ),
                    "details": {**replenishment},
                }
        if replenishment["status"] in {"reorder", "out_of_stock"}:
            reorder_count += 1

        previous = previous_snapshots.get(variant.id)
        if (
            previous
            and previous.cost_price
            and cost_price is not None
            and previous.cost_price > 0
        ):
            increase_rate = (cost_price - previous.cost_price) / previous.cost_price * 100
            if increase_rate >= setting.cost_increase_alert_rate:
                key = _alert_key("cost_increase", variant.id, product.id)
                desired[key] = {
                    "alert_type": "cost_increase",
                    "variant_id": variant.id,
                    "product_id": product.id,
                    "sku": variant.sku,
                    "severity": "warning",
                    "title": "供货成本上涨",
                    "message": (
                        f"{variant.sku} 成本较上次快照上涨 {increase_rate:.1f}%，"
                        f"请复核售价和毛利。"
                    ),
                    "details": {
                        "previous_cost": previous.cost_price,
                        "current_cost": cost_price,
                        "increase_rate": round(increase_rate, 2),
                    },
                }

        items.append(
            {
                "variant_id": str(variant.id),
                "product_id": str(product.id),
                "product_title": product.title,
                "sku": variant.sku,
                "selling_price": variant.price,
                "cost_price": cost_price,
                "stock_quantity": variant.stock_quantity,
                "daily_sales_rate": variant.daily_sales_rate,
                "margin_rate": margin["margin_rate"],
                "net_profit": margin["net_profit"],
                **replenishment,
            }
        )

    for product_id, product_variants in variants_by_product.items():
        product = next(row[1] for row in rows if row[1].id == product_id)
        if not product.main_image_url and not any(item.image_url for item in product_variants):
            key = _alert_key("missing_image", None, product_id)
            desired[key] = {
                "alert_type": "missing_image",
                "variant_id": None,
                "product_id": product_id,
                "sku": None,
                "severity": "warning",
                "title": "商品缺主图",
                "message": f"{product.title or '未命名商品'} 还没有商品主图或变体图。",
                "details": {},
            }

    for listing in blocked_listings:
        key = _alert_key("listing_blocked", None, listing.product_id)
        desired[key] = {
            "alert_type": "listing_blocked",
            "variant_id": None,
            "product_id": listing.product_id,
            "sku": None,
            "severity": "error",
            "title": "Listing 合规阻断",
            "message": f"{listing.platform} Listing 命中合规规则，修改并复审前不能发布。",
            "details": {"listing_id": str(listing.id), "platform": listing.platform},
        }

    now = datetime.now(timezone.utc)
    for key, alert_data in desired.items():
        existing = active_alerts.get(key)
        if existing:
            existing.title = alert_data["title"]
            existing.message = alert_data["message"]
            existing.severity = alert_data["severity"]
            existing.details_json = json.dumps(alert_data["details"], ensure_ascii=False)
        else:
            db.add(
                OperationAlert(
                    user_id=user.id,
                    alert_type=alert_data["alert_type"],
                    variant_id=alert_data["variant_id"],
                    product_id=alert_data["product_id"],
                    sku=alert_data["sku"],
                    severity=alert_data["severity"],
                    title=alert_data["title"],
                    message=alert_data["message"],
                    details_json=json.dumps(alert_data["details"], ensure_ascii=False),
                    status="open",
                )
            )

    for key, existing in active_alerts.items():
        if key not in desired:
            existing.status = "resolved"
            existing.updated_at = now

    await db.flush()
    pending_count = sum(
        1
        for key in desired
        if key not in active_alerts or active_alerts[key].status == "open"
    )
    return {
        "sku_count": len(rows),
        "low_stock_count": low_stock_count,
        "low_margin_count": low_margin_count,
        "reorder_count": reorder_count,
        "open_alerts": pending_count,
        "items": items,
        "settings": serialize_settings(setting),
    }


async def scan_all_users(db: AsyncSession) -> int:
    """供每日调度器扫描拥有 SKU 的所有用户。"""
    user_ids = (
        await db.execute(select(ProductVariant.user_id).distinct())
    ).scalars().all()
    count = 0
    for user_id in user_ids:
        user = await db.get(User, user_id)
        if user:
            await run_monitor_scan(db, user)
            count += 1
    return count


async def refresh_supplier_costs(db: AsyncSession, user: User) -> dict[str, Any]:
    """使用平台抓取链刷新 1688 供货价，并补齐未手工设置成本的 SKU。"""
    await provider_config.refresh(db)
    products = (
        await db.execute(
            select(Product)
            .where(Product.user_id == user.id, Product.url.is_not(None))
            .order_by(desc(Product.updated_at))
            .limit(50)
        )
    ).scalars().all()

    refreshed = 0
    failed = 0
    failures: list[dict[str, str]] = []
    for product in products:
        try:
            data = await scrape_1688(
                product.url,
                justone_token=provider_config.get("justone", "token"),
                api_key=provider_config.get("onebound", "api_key"),
                api_secret=provider_config.get("onebound", "api_secret"),
            )
            new_price = data.get("price")
            if new_price is None:
                failed += 1
                failures.append({"product_id": str(product.id), "error": "未返回供货价"})
                continue
            product.price = float(new_price)
            variants = (
                await db.execute(
                    select(ProductVariant).where(
                        ProductVariant.product_id == product.id,
                        ProductVariant.user_id == user.id,
                        ProductVariant.cost_price.is_(None),
                    )
                )
            ).scalars().all()
            for variant in variants:
                variant.cost_price = float(new_price)
            refreshed += 1
        except Exception as exc:
            failed += 1
            failures.append({"product_id": str(product.id), "error": str(exc)})

    await db.flush()
    return {
        "refreshed": refreshed,
        "failed": failed,
        "failures": failures,
        "total": len(products),
    }
