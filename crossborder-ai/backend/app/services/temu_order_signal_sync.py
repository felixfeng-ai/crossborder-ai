"""Temu LOCAL/SEMI 订单巡检与 Agent 工作项同步。"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_connection import PlatformConnection
from app.models.workspace import Workspace
from app.services.agent_signals import (
    ingest_agent_signal,
    resolve_latest_signal_by_fingerprint,
    save_integration_cursor,
)
from app.services.integration_events import (
    claim_integration_lease,
    release_integration_lease,
)
from app.services.temu_capabilities import derive_temu_capabilities
from app.services.temu_order_read import TemuOrderReadService


ORDER_PAGE_SIZE = 100
MAX_ORDER_PAGES = 20
ATTENTION_WINDOW_HOURS = 24


def _timestamp(value) -> datetime | None:
    """兼容 Temu 秒级时间戳和 ISO 时间，无法识别时返回空。"""

    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            return None
        return parsed if parsed.tzinfo else parsed.replace(
            tzinfo=timezone.utc
        )
    if numeric > 10_000_000_000:
        numeric /= 1000
    return datetime.fromtimestamp(numeric, tz=timezone.utc)


def _quantity(value) -> int:
    """商品数量异常时按 0 处理，避免一条脏数据中断整店巡检。"""

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _work_item_state(
    order: dict,
    *,
    now: datetime | None = None,
) -> dict | None:
    """判断订单是否需要进入履约关注，不解释未知订单状态码。"""

    current = now or datetime.now(timezone.utc)
    raw_warnings = order.get("fulfillment_warnings") or []
    if not isinstance(raw_warnings, (list, tuple, set)):
        raw_warnings = [raw_warnings]
    warnings = [
        str(value)
        for value in raw_warnings
        if str(value).strip()
    ]
    deadline = _timestamp(order.get("expect_ship_latest_time"))
    inside_window = (
        deadline is not None
        and deadline <= current + timedelta(hours=ATTENTION_WINDOW_HOURS)
    )
    if not warnings and not inside_window:
        return None
    overdue = deadline is not None and deadline <= current
    severity = (
        "urgent"
        if overdue
        else "attention"
        if warnings or inside_window
        else "normal"
    )
    orders = [
        item
        for item in order.get("orders") or []
        if isinstance(item, dict)
    ]
    return {
        "severity": severity,
        "warnings": warnings,
        "deadline": deadline,
        "item_count": sum(
            _quantity(item.get("quantity"))
            for item in orders
        ),
        "line_count": len(orders),
    }


def _all_order_lines_shipped(order: dict) -> bool:
    """所有订单行都有有效发货时间时才视为已发货。"""

    orders = [
        item
        for item in order.get("orders") or []
        if isinstance(item, dict)
    ]
    if not orders:
        return False
    for item in orders:
        value = item.get("shipping_time")
        if value in (None, "", 0, "0"):
            return False
        if _timestamp(value) is None:
            return False
    return True


def _order_read_eligible(connection: PlatformConnection) -> bool:
    """只让有 v2 订单 scope 的 LOCAL/SEMI 店铺进入自动巡检。"""

    try:
        metadata = json.loads(connection.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(metadata, dict):
        return False
    store_type = str(metadata.get("store_type") or "").strip().lower()
    if store_type not in {"local", "semi"}:
        return False
    capabilities = derive_temu_capabilities(
        metadata.get("api_scope_list") or [],
        store_type=store_type,
    )
    order_read = capabilities["order.read"]
    return bool(
        order_read["available"]
        and "bg.order.list.v2.get" in order_read["scopes"]
    )


async def _workspace_for_connection(
    db: AsyncSession,
    connection: PlatformConnection,
) -> Workspace:
    workspace = (
        await db.execute(
            select(Workspace)
            .where(
                Workspace.owner_user_id == connection.user_id,
                Workspace.type == "personal",
                Workspace.status == "active",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise ValueError("Temu 店铺不属于当前个人工作区")
    return workspace


async def _load_orders(
    db: AsyncSession,
    *,
    connection: PlatformConnection,
) -> tuple[list[dict], int]:
    """读取完整订单批次；任何一页失败都不产生部分工作项。"""

    service = TemuOrderReadService(db, user_id=connection.user_id)
    orders: list[dict] = []
    page_number = 1
    total = 0
    while page_number <= MAX_ORDER_PAGES:
        page = await service.list_orders(
            connection_id=connection.id,
            page_number=page_number,
            page_size=ORDER_PAGE_SIZE,
        )
        total = max(0, int(page.get("total") or 0))
        items = [
            item
            for item in page.get("items") or []
            if isinstance(item, dict)
        ]
        orders.extend(items)
        if not items or len(orders) >= total:
            return orders, page_number
        page_number += 1
    raise RuntimeError("Temu 待巡检订单超过单次同步上限")


async def sync_temu_order_signals(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    connection: PlatformConnection,
) -> dict:
    """巡检单个 Temu 店铺并生成履约关注工作项。"""

    workspace = await db.get(Workspace, workspace_id)
    if (
        workspace is None
        or workspace.type != "personal"
        or workspace.owner_user_id != connection.user_id
    ):
        raise ValueError("Temu 店铺不属于当前个人工作区")
    if connection.platform != "temu" or connection.status != "active":
        raise ValueError("Temu 店铺连接不可用")

    orders, pages = await _load_orders(db, connection=connection)
    created = 0
    updated = 0
    resolved = 0
    latest_updated = 0
    for order in orders:
        parent_order_sn = str(
            order.get("parent_order_sn") or ""
        ).strip()
        if not parent_order_sn:
            continue
        try:
            latest_updated = max(
                latest_updated,
                int(order.get("updated_time") or 0),
            )
        except (TypeError, ValueError):
            pass
        fingerprint = (
            f"temu-order:{connection.id}:{parent_order_sn}:shipment-due"
        )
        state = _work_item_state(order)
        if _all_order_lines_shipped(order) or state is None:
            resolved_signal = await resolve_latest_signal_by_fingerprint(
                db,
                workspace_id=workspace_id,
                fingerprint=fingerprint,
                summary="Temu 订单已完成发货或履约风险已消失。",
            )
            if resolved_signal is not None:
                resolved += 1
            continue
        deadline = state["deadline"]
        result = await ingest_agent_signal(
            db,
            workspace_id=workspace_id,
            actor_user_id=connection.user_id,
            source_type="temu_order",
            source_id=parent_order_sn,
            signal_type="temu_order_awaiting_shipment",
            severity=state["severity"],
            title=f"Temu 订单 {parent_order_sn} 临近发货时限",
            summary=(
                f"{state['item_count'] or state['line_count']} 件商品"
                + (
                    " · 最迟发货时间 "
                    + deadline.strftime("%Y-%m-%d %H:%M UTC")
                    if deadline is not None
                    else ""
                )
            ),
            payload={
                "parent_order_sn": parent_order_sn,
                "parent_order_status": order.get("parent_order_status"),
                "item_count": state["item_count"],
                "line_count": state["line_count"],
                "fulfillment_warnings": state["warnings"],
                "expect_ship_latest_time": order.get(
                    "expect_ship_latest_time"
                ),
            },
            fingerprint=fingerprint,
            channel_type="temu",
            channel_id=str(connection.id),
        )
        if result.created:
            created += 1
        else:
            updated += 1

    cursor_value = str(latest_updated or int(datetime.now().timestamp()))
    await save_integration_cursor(
        db,
        workspace_id=workspace_id,
        channel_id=f"temu:{connection.id}",
        resource_type="temu_orders",
        cursor_value=cursor_value,
        overlap_seconds=0,
    )
    return {
        "orders_scanned": len(orders),
        "pages_scanned": pages,
        "signals_created": created,
        "signals_updated": updated,
        "signals_resolved": resolved,
        "cursor_value": cursor_value,
    }


async def sync_all_temu_order_signals(db: AsyncSession) -> dict:
    """同步全部有效 Temu 店铺，单店失败不阻塞其他店铺。"""

    connections = (
        await db.execute(
            select(PlatformConnection).where(
                PlatformConnection.platform == "temu",
                PlatformConnection.status == "active",
            )
        )
    ).scalars().all()
    summary = {
        "connections_scanned": len(connections),
        "connections_succeeded": 0,
        "connections_failed": 0,
        "connections_skipped": 0,
        "signals_created": 0,
        "signals_resolved": 0,
        "failures": [],
    }
    for connection in connections:
        connection_id = connection.id
        if not _order_read_eligible(connection):
            summary["connections_skipped"] += 1
            continue
        try:
            workspace = await _workspace_for_connection(db, connection)
        except ValueError:
            summary["connections_skipped"] += 1
            continue
        workspace_id = workspace.id
        channel_id = f"temu:{connection_id}"
        owner = f"temu-order-sync:{uuid4().hex}"
        lease = await claim_integration_lease(
            db,
            workspace_id=workspace_id,
            channel_id=channel_id,
            resource_type="temu_orders",
            owner_token=owner,
            ttl_seconds=600,
        )
        await db.commit()
        if lease is None:
            summary["connections_skipped"] += 1
            continue
        try:
            result = await sync_temu_order_signals(
                db,
                workspace_id=workspace_id,
                connection=connection,
            )
            await db.commit()
            summary["connections_succeeded"] += 1
            summary["signals_created"] += result["signals_created"]
            summary["signals_resolved"] += result["signals_resolved"]
        except Exception as exc:
            await db.rollback()
            summary["connections_failed"] += 1
            summary["failures"].append(
                {
                    "connection_id": str(connection_id),
                    "error": str(exc)[:200],
                }
            )
        finally:
            await release_integration_lease(
                db,
                workspace_id=workspace_id,
                channel_id=channel_id,
                resource_type="temu_orders",
                owner_token=owner,
            )
            await db.commit()
    return summary
