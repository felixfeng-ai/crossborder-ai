"""Temu 商品提交后的原始状态追踪与工作项同步。"""

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_signal import AgentSignal
from app.models.agent_work import WorkItem
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.workspace import Workspace
from app.services.agent_signals import (
    SignalIngestResult,
    ingest_agent_signal,
    resolve_agent_signal,
)
from app.services.temu_listing_publish import TemuListingPublishService


def listing_status_fingerprint(
    connection_id: UUID,
    goods_id: int,
) -> str:
    return f"temu-listing:{connection_id}:{goods_id}:processing"


def interpret_temu_listing_status(
    status,
    sub_status,
    *,
    status_map: dict[tuple[int, int], str] | None = None,
) -> str:
    """只按显式映射解释状态；默认不把任何整数推断成最终结果。"""

    try:
        key = (int(status), int(sub_status))
    except (TypeError, ValueError):
        return "processing"
    return (status_map or {}).get(key, "processing")


async def register_temu_listing_submission(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    connection_id: UUID,
    listing_id: UUID,
    goods_id: int,
    external_goods_id: str,
    raw_status=None,
    raw_sub_status=None,
) -> SignalIngestResult:
    """登记或刷新一个已提交 Temu 商品的平台处理信号。"""

    listing = (
        await db.execute(
            select(ListingDraft).where(
                ListingDraft.id == listing_id,
                ListingDraft.workspace_id == workspace_id,
                ListingDraft.platform == "temu",
            )
        )
    ).scalar_one_or_none()
    if listing is None:
        raise ValueError("Temu Listing 不存在或不属于当前工作区")
    connection = (
        await db.execute(
            select(PlatformConnection).where(
                PlatformConnection.id == connection_id,
                PlatformConnection.platform == "temu",
                PlatformConnection.status == "active",
            )
        )
    ).scalar_one_or_none()
    if connection is None:
        raise ValueError("Temu 店铺连接不存在或授权不可用")
    workspace = await db.get(Workspace, workspace_id)
    if (
        workspace is None
        or workspace.owner_user_id != connection.user_id
    ):
        raise ValueError("Temu 店铺不属于当前工作区")
    external_id = str(external_goods_id or "").strip()
    return await ingest_agent_signal(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        source_type="temu_listing",
        source_id=str(goods_id),
        signal_type="temu_listing_processing",
        severity="normal",
        title=f"Temu 商品 {goods_id} 正在处理",
        summary=(
            "Temu 已受理商品提交，原始状态 "
            f"{raw_status if raw_status is not None else 'unknown'}"
            " / "
            f"{raw_sub_status if raw_sub_status is not None else 'unknown'}"
        ),
        payload={
            "connection_id": str(connection_id),
            "listing_id": str(listing_id),
            "goods_id": int(goods_id),
            "external_goods_id": external_id,
            "raw_status": raw_status,
            "raw_sub_status": raw_sub_status,
            "state": "processing",
        },
        fingerprint=listing_status_fingerprint(connection_id, goods_id),
    )


def _payload(signal: AgentSignal) -> dict:
    try:
        value = json.loads(signal.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


async def sync_all_temu_listing_statuses(
    db: AsyncSession,
    *,
    status_map: dict[tuple[int, int], str] | None = None,
    limit: int = 200,
) -> dict:
    """批量刷新开放 Temu 商品信号，按店铺隔离失败。"""

    signals = (
        await db.execute(
            select(AgentSignal)
            .where(
                AgentSignal.signal_type == "temu_listing_processing",
                AgentSignal.status.in_(
                    {"new", "grouped", "task_created"}
                ),
            )
            .order_by(AgentSignal.observed_at, AgentSignal.id)
            .limit(max(1, limit))
        )
    ).scalars().all()
    summary = {
        "signals_scanned": len(signals),
        "connections_scanned": 0,
        "signals_updated": 0,
        "signals_resolved": 0,
        "signals_pending": 0,
        "failure_count": 0,
        "failures": [],
    }
    grouped: dict[tuple[UUID, UUID], list[AgentSignal]] = {}
    for signal in signals:
        payload = _payload(signal)
        try:
            connection_id = UUID(str(payload["connection_id"]))
            goods_id = int(payload["goods_id"])
        except (KeyError, TypeError, ValueError):
            summary["failure_count"] += 1
            summary["failures"].append(
                {
                    "signal_id": str(signal.id),
                    "error": "信号缺少连接或商品编号",
                }
            )
            continue
        if goods_id <= 0:
            continue
        grouped.setdefault(
            (signal.workspace_id, connection_id),
            [],
        ).append(signal)
    for (workspace_id, connection_id), group in grouped.items():
        summary["connections_scanned"] += 1
        connection = await db.get(PlatformConnection, connection_id)
        if connection is None or connection.platform != "temu":
            summary["failure_count"] += 1
            summary["failures"].append(
                {
                    "connection_id": str(connection_id),
                    "error": "Temu 店铺连接不存在",
                }
            )
            continue
        service = TemuListingPublishService(
            db,
            user_id=connection.user_id,
        )
        goods_ids = [
            int(_payload(item).get("goods_id") or 0)
            for item in group
        ]
        try:
            remote_rows = await service.get_publish_statuses(
                connection_id=connection_id,
                goods_ids=goods_ids,
            )
        except Exception as exc:
            summary["failure_count"] += 1
            summary["failures"].append(
                {
                    "connection_id": str(connection_id),
                    "error": str(exc)[:200],
                }
            )
            continue
        by_goods = {
            int(item["goods_id"]): item
            for item in remote_rows
            if int(item.get("goods_id") or 0) > 0
        }
        for signal in group:
            payload = _payload(signal)
            goods_id = int(payload.get("goods_id") or 0)
            remote = by_goods.get(goods_id)
            if remote is None:
                summary["signals_pending"] += 1
                continue
            outcome = interpret_temu_listing_status(
                remote.get("status"),
                remote.get("sub_status"),
                status_map=status_map,
            )
            observation_count = (
                int(payload.get("observation_count") or 0) + 1
            )
            latest_payload = {
                **payload,
                "raw_status": remote.get("status"),
                "raw_sub_status": remote.get("sub_status"),
                "state": outcome,
                "observation_count": observation_count,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            severity = "urgent" if outcome == "rejected" else "normal"
            title = (
                f"Temu 商品 {goods_id} 需要处理"
                if outcome == "rejected"
                else f"Temu 商品 {goods_id} 正在处理"
            )
            ingest = await ingest_agent_signal(
                db,
                workspace_id=workspace_id,
                actor_user_id=connection.user_id,
                source_type="temu_listing",
                source_id=str(goods_id),
                signal_type="temu_listing_processing",
                severity=severity,
                title=title,
                summary=(
                    f"Temu 原始状态 {remote.get('status')} / "
                    f"{remote.get('sub_status')}"
                ),
                payload=latest_payload,
                fingerprint=listing_status_fingerprint(
                    connection_id,
                    goods_id,
                ),
            )
            summary["signals_updated"] += 1
            if outcome == "succeeded":
                await resolve_agent_signal(
                    db,
                    workspace_id=workspace_id,
                    signal_id=ingest.signal.id,
                    summary="Temu 商品已通过发布状态映射。",
                )
                listing_id = str(payload.get("listing_id") or "")
                try:
                    listing = await db.get(
                        ListingDraft,
                        UUID(listing_id),
                    )
                except (TypeError, ValueError):
                    listing = None
                if listing is not None:
                    listing.status = "published"
                    listing.published_at = datetime.now(timezone.utc)
                summary["signals_resolved"] += 1
            elif outcome == "rejected" and ingest.work_item is not None:
                ingest.work_item.status = "waiting_user"
                ingest.work_item.requires_action = "choose"
                ingest.work_item.current_step = (
                    "Temu 返回需处理状态"
                )
    await db.flush()
    return summary
