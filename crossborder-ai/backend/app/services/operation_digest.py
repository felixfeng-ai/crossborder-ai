"""经营预警摘要、优先级排序和整改动作映射。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_alert import OperationAlert


SEVERITY_RANK = {"critical": 4, "error": 3, "warning": 2, "info": 1}
ALERT_ACTIONS = {
    "missing_price": "补齐 SKU 售价后重新扫描",
    "missing_cost": "同步供货价或手工补充成本",
    "low_margin": "复核售价、成本和平台费率",
    "sales_data_missing": "同步 Shopify 销量或手工填写日均销量",
    "out_of_stock": "立即补货，必要时暂停广告和促销",
    "low_stock": "按建议数量安排补货",
    "cost_increase": "复核供货成本并及时调整售价",
    "missing_image": "上传商品主图后重新检查",
    "listing_blocked": "修改违规 Listing 并重新执行合规审查",
}


def build_operation_digest(
    alerts: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """把开放预警整理成可直接执行和追踪的优先级摘要。"""
    ordered = sorted(
        alerts,
        key=lambda item: (
            -SEVERITY_RANK.get(str(item.get("severity") or ""), 0),
            str(item.get("created_at") or ""),
        ),
    )
    severity_counts = {
        level: sum(item.get("severity") == level for item in ordered)
        for level in ("critical", "error", "warning", "info")
    }
    immediate = severity_counts["critical"] + severity_counts["error"]
    total = len(ordered)
    highest_severity = (
        str(ordered[0].get("severity") or "") if ordered else None
    )
    priority_items = []
    for item in ordered[: max(1, min(limit, 20))]:
        priority_items.append(
            {
                "id": str(item.get("id") or ""),
                "product_id": item.get("product_id"),
                "variant_id": item.get("variant_id"),
                "sku": item.get("sku"),
                "alert_type": str(item.get("alert_type") or ""),
                "severity": str(item.get("severity") or "info"),
                "title": str(item.get("title") or "经营预警"),
                "message": str(item.get("message") or ""),
                "suggested_action": str(
                    item.get("suggested_action")
                    or ALERT_ACTIONS.get(
                        str(item.get("alert_type") or ""),
                        "打开运营监控查看详情并处理",
                    )
                ),
                "action_href": str(
                    item.get("action_href")
                    or (
                        f"/app/products/{item.get('product_id')}"
                        if item.get("product_id")
                        else "/app/operations"
                    )
                ),
            }
        )
    if total == 0:
        headline = "暂无待处理经营预警"
    elif immediate:
        headline = f"{total} 项经营预警，{immediate} 项需要立即处理"
    else:
        headline = f"{total} 项经营预警，建议按优先级处理"
    return {
        "total": total,
        "highest_severity": highest_severity,
        "severity_counts": severity_counts,
        "headline": headline,
        "priority_items": priority_items,
    }


async def get_operation_digest(
    db: AsyncSession,
    *,
    user_id,
    limit: int = 5,
) -> dict[str, Any]:
    """读取当前开放预警，不触发新的运营扫描。"""
    from app.services.operations_monitor import serialize_alert

    rows = (
        await db.execute(
            select(OperationAlert).where(
                OperationAlert.user_id == user_id,
                OperationAlert.status == "open",
            )
        )
    ).scalars().all()
    return build_operation_digest(
        [serialize_alert(alert) for alert in rows],
        limit=limit,
    )
