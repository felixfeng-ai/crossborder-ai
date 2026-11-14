"""管理员运营分析查询。"""

from datetime import datetime, timedelta, timezone
from math import floor

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_purchase import CreditPurchase
from app.models.feedback import FeedbackTicket
from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.traffic_event import TrafficEvent
from app.models.user import User


WEB_VITAL_NAMES = ("LCP", "FCP", "INP", "CLS", "TTFB")


def _percentile(values: list[float], percentile: float) -> float | None:
    """线性插值计算分位数，保持 SQLite 与 PostgreSQL 行为一致。"""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return round(ordered[lower], 2)
    ratio = position - lower
    return round(ordered[lower] * (1 - ratio) + ordered[upper] * ratio, 2)


def _date_key(value) -> str:
    """兼容 SQLite 返回字符串、PostgreSQL 返回 date 的日期分组。"""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


async def build_admin_analytics_overview(
    db: AsyncSession,
    *,
    days: int = 7,
) -> dict:
    """生成管理员总览需要的业务、流量和性能摘要。"""
    safe_days = max(1, min(days, 90))
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=safe_days)

    event_filter = (
        TrafficEvent.created_at >= cutoff,
        TrafficEvent.is_bot.is_(False),
    )
    page_filter = (*event_filter, TrafficEvent.event_type == "page_view")

    pv = await db.scalar(
        select(func.count(TrafficEvent.id)).where(*page_filter)
    ) or 0
    uv = await db.scalar(
        select(func.count(func.distinct(TrafficEvent.visitor_id))).where(*page_filter)
    ) or 0
    sessions = await db.scalar(
        select(func.count(func.distinct(TrafficEvent.session_id))).where(*page_filter)
    ) or 0

    daily_rows = (
        await db.execute(
            select(
                func.date(TrafficEvent.created_at).label("day"),
                func.count(TrafficEvent.id).label("pv"),
                func.count(func.distinct(TrafficEvent.visitor_id)).label("uv"),
            )
            .where(*page_filter)
            .group_by(func.date(TrafficEvent.created_at))
            .order_by(func.date(TrafficEvent.created_at))
        )
    ).all()
    daily = [
        {"date": _date_key(row.day), "pv": int(row.pv or 0), "uv": int(row.uv or 0)}
        for row in daily_rows
    ]

    path_rows = (
        await db.execute(
            select(
                TrafficEvent.path,
                func.count(TrafficEvent.id).label("pv"),
                func.count(func.distinct(TrafficEvent.visitor_id)).label("uv"),
            )
            .where(*page_filter)
            .group_by(TrafficEvent.path)
            .order_by(func.count(TrafficEvent.id).desc())
            .limit(8)
        )
    ).all()
    paths = [
        {"path": row.path, "pv": int(row.pv or 0), "uv": int(row.uv or 0)}
        for row in path_rows
    ]

    device_rows = (
        await db.execute(
            select(TrafficEvent.device_type, func.count(TrafficEvent.id))
            .where(*page_filter)
            .group_by(TrafficEvent.device_type)
        )
    ).all()
    devices = [
        {"device": str(name or "unknown"), "pv": int(count or 0)}
        for name, count in device_rows
    ]

    country_rows = (
        await db.execute(
            select(TrafficEvent.country_code, func.count(TrafficEvent.id))
            .where(*page_filter)
            .group_by(TrafficEvent.country_code)
        )
    ).all()
    countries = [
        {"country": str(name or "unknown"), "pv": int(count or 0)}
        for name, count in country_rows
    ]

    vital_rows = (
        await db.execute(
            select(
                TrafficEvent.metric_name,
                TrafficEvent.metric_value,
                TrafficEvent.metric_rating,
                TrafficEvent.country_code,
                TrafficEvent.device_type,
                TrafficEvent.connection_type,
            ).where(*event_filter, TrafficEvent.event_type == "web_vital")
        )
    ).all()
    metric_values: dict[str, list[float]] = {name: [] for name in WEB_VITAL_NAMES}
    metric_ratings: dict[str, dict[str, int]] = {
        name: {"good": 0, "needs-improvement": 0, "poor": 0}
        for name in WEB_VITAL_NAMES
    }
    for name, value, rating, _country, _device, _connection in vital_rows:
        if name not in metric_values or value is None:
            continue
        metric_values[name].append(float(value))
        if rating in metric_ratings[name]:
            metric_ratings[name][rating] += 1
    metrics = {
        name: {
            "samples": len(metric_values[name]),
            "p75": _percentile(metric_values[name], 0.75),
            "ratings": metric_ratings[name],
        }
        for name in WEB_VITAL_NAMES
    }
    group_filters = {
        "all": lambda country, device, connection: True,
        "china": lambda country, device, connection: country == "CN",
        "overseas": lambda country, device, connection: country
        not in {"CN", "UNKNOWN", "unknown", ""},
        "mobile": lambda country, device, connection: device == "mobile"
        or connection in {"slow-2g", "2g", "3g", "4g"},
    }
    performance_groups = {}
    for group_name, predicate in group_filters.items():
        group_values: dict[str, list[float]] = {name: [] for name in WEB_VITAL_NAMES}
        group_ratings: dict[str, dict[str, int]] = {
            name: {"good": 0, "needs-improvement": 0, "poor": 0}
            for name in WEB_VITAL_NAMES
        }
        for name, value, rating, country, device, connection in vital_rows:
            if (
                name not in group_values
                or value is None
                or not predicate(
                    str(country or ""),
                    str(device or ""),
                    str(connection or ""),
                )
            ):
                continue
            group_values[name].append(float(value))
            if rating in group_ratings[name]:
                group_ratings[name][rating] += 1
        performance_groups[group_name] = {
            "metrics": {
                name: {
                    "samples": len(group_values[name]),
                    "p75": _percentile(group_values[name], 0.75),
                    "ratings": group_ratings[name],
                }
                for name in WEB_VITAL_NAMES
            }
        }

    total_users = await db.scalar(select(func.count(User.id))) or 0
    paid_users = await db.scalar(
        select(func.count(User.id)).where(User.plan.in_(("standard", "professional")))
    ) or 0
    plan_rows = (
        await db.execute(
            select(User.plan, func.count(User.id)).group_by(User.plan)
        )
    ).all()
    plan_distribution = {
        str(plan or "free"): int(count or 0) for plan, count in plan_rows
    }
    pending_upgrades = await db.scalar(
        select(func.count(PlanUpgradeRequest.id)).where(
            PlanUpgradeRequest.status == "pending"
        )
    ) or 0
    pending_credit_purchases = await db.scalar(
        select(func.count(CreditPurchase.id)).where(CreditPurchase.status == "pending")
    ) or 0
    open_feedback = await db.scalar(
        select(func.count(FeedbackTicket.id)).where(
            FeedbackTicket.status.in_(("open", "in_progress"))
        )
    ) or 0

    upgrade_revenue = await db.scalar(
        select(func.coalesce(func.sum(PlanUpgradeRequest.amount), 0)).where(
            PlanUpgradeRequest.status == "approved",
            PlanUpgradeRequest.handled_at >= cutoff,
        )
    ) or 0
    credit_revenue = await db.scalar(
        select(func.coalesce(func.sum(CreditPurchase.amount), 0)).where(
            CreditPurchase.status == "approved",
            CreditPurchase.handled_at >= cutoff,
        )
    ) or 0

    return {
        "range_days": safe_days,
        "business": {
            "total_users": int(total_users),
            "paid_users": int(paid_users),
            "plan_distribution": plan_distribution,
            "pending_upgrades": int(pending_upgrades),
            "pending_credit_purchases": int(pending_credit_purchases),
            "feedback_open": int(open_feedback),
            "revenue": round(float(upgrade_revenue) + float(credit_revenue), 2),
        },
        "traffic": {
            "pv": int(pv),
            "uv": int(uv),
            "sessions": int(sessions),
            "daily": daily,
            "top_paths": paths,
            "devices": devices,
            "countries": countries,
        },
        "performance": {
            "metrics": metrics,
            "groups": performance_groups,
        },
    }
