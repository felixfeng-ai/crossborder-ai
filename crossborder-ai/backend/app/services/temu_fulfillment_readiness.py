"""Temu 自发货只读验收诊断。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.temu_fulfillment_adapter import (
    TemuOrderFulfillmentActionAdapter,
)


ACTION_ID = "temu.orders.fulfill"


def readiness_exit_code(report: dict) -> int:
    """只读诊断只在 ready 时返回成功，供 CLI 和 CI 统一使用。"""

    return 0 if report.get("ready") is True else 2


def _mask_tracking_number(value: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:4]}...{normalized[-4:]}"


def build_temu_fulfillment_readiness_report(
    snapshot: dict | None = None,
    *,
    error: str | None = None,
    connection_id: str = "",
    parent_order_sn: str = "",
) -> dict:
    """把预检快照转换成可审计、不可误触发提交的只读报告。"""

    data = snapshot or {}
    blockers = [error[:400]] if error else []
    if not error and data.get("already_shipped"):
        blockers.append("订单已经发货，不能用于首次自发货提交验收")
    ready = not blockers
    tracking_number = str(data.get("tracking_number") or "")
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "submitted": False,
        "action_id": ACTION_ID,
        "connection_id": str(
            data.get("connection_id") or connection_id
        ),
        "parent_order_sn": str(
            data.get("parent_order_sn") or parent_order_sn
        ),
        "region_id": data.get("region_id"),
        "carrier": {
            "carrier_id": data.get("carrier_id"),
            "name": str(data.get("carrier_name") or ""),
        },
        "tracking_number_masked": _mask_tracking_number(
            tracking_number
        ),
        "self_shipping_warehouse_present": bool(
            str(
                data.get("self_shipping_warehouse_id") or ""
            ).strip()
        ),
        "item_count": int(data.get("item_count") or 0),
        "order_sn_count": len(data.get("order_sns") or []),
        "already_shipped": bool(data.get("already_shipped")),
        "blockers": blockers,
        "next_step": (
            "在 App 中确认 temu.orders.fulfill 动作并回读物流单号"
            if ready
            else "修复阻断项后重新执行只读预检"
        ),
    }


async def run_temu_fulfillment_readiness(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID,
    connection_id: UUID,
    parent_order_sn: str,
    carrier_id: int,
    tracking_number: str,
    self_shipping_warehouse_id: str = "",
    adapter: TemuOrderFulfillmentActionAdapter | None = None,
) -> dict:
    """执行只读预检；此函数从不调用适配器 execute。"""

    selected_adapter = adapter or TemuOrderFulfillmentActionAdapter(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    input_data = {
        "connection_id": str(connection_id),
        "parent_order_sn": str(parent_order_sn or "").strip(),
        "carrier_id": int(carrier_id),
        "tracking_number": str(tracking_number or "").strip(),
        "self_shipping_warehouse_id": str(
            self_shipping_warehouse_id or ""
        ).strip(),
    }
    try:
        snapshot = await selected_adapter.preflight(
            action_id=ACTION_ID,
            target_id=input_data["parent_order_sn"],
            input_data=input_data,
        )
    except Exception as exc:
        return build_temu_fulfillment_readiness_report(
            error=str(exc),
            connection_id=str(connection_id),
            parent_order_sn=input_data["parent_order_sn"],
        )
    return build_temu_fulfillment_readiness_report(
        snapshot,
        connection_id=str(connection_id),
        parent_order_sn=input_data["parent_order_sn"],
    )
