"""把平台事实归一化为 Agent 信号并映射为工作项。"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_signal import AgentSignal, IntegrationCursor
from app.models.agent_work import WorkItem
from app.services.work_items import create_work_item


@dataclass
class SignalIngestResult:
    """一次信号归一化的结果，区分新任务和聚合更新。"""

    created: bool
    signal: AgentSignal
    work_item: WorkItem


SIGNAL_WORK_ITEM_RULES = {
    "order_delay": {
        "kind": "order_exception",
        "requires_action": "confirm",
        "current_step": "等待你决定是否给买家发送延迟说明",
    },
    "order_awaiting_shipment": {
        "kind": "order_exception",
        "requires_action": "confirm",
        "current_step": "订单等待发货，Agent 已准备履约方案",
    },
    "amazon_order_awaiting_shipment": {
        "kind": "order_exception",
        "requires_action": "none",
        "current_step": "Amazon 订单等待发货，Agent 正在核对履约条件",
    },
    "temu_order_awaiting_shipment": {
        "kind": "order_exception",
        "requires_action": "none",
        "current_step": "Temu 订单临近发货时限，Agent 正在核对履约条件",
    },
    "temu_listing_processing": {
        "kind": "listing_action",
        "requires_action": "none",
        "current_step": "商品已提交到 Temu，等待平台处理",
    },
    "customer_message": {
        "kind": "customer_reply",
        "requires_action": "confirm",
        "current_step": "回复草稿已准备",
    },
    "inventory_low": {
        "kind": "inventory_action",
        "requires_action": "none",
        "current_step": "Agent 正在评估补货和库存调整",
    },
    "inventory_out_of_stock": {
        "kind": "inventory_action",
        "requires_action": "confirm",
        "current_step": "库存已缺货，等待你决定补货或暂停销售",
    },
    "inventory_conflict": {
        "kind": "inventory_action",
        "requires_action": "confirm",
        "current_step": "平台库存与本地库存不一致，需要确认处理方式",
    },
    "authorization_expired": {
        "kind": "connection_action",
        "requires_action": "confirm",
        "current_step": "店铺授权失效，需要重新连接",
    },
    "refund_pending": {
        "kind": "refund_action",
        "requires_action": "confirm",
        "current_step": "等待你确认退款方案",
    },
}


def _payload(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _commerce_payload(raw: str | None) -> dict | None:
    """取出信号里的交易事实子树，随工作项一起落库。

    只透传，不做业务校验 —— 清洗和兜底统一放在读取端（timeline 序列化），
    这样写入侧永远只存平台给的原始值，不会出现两套规则。
    """
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("commerce")
    return value if isinstance(value, dict) else None


def _attach_commerce(work_item: WorkItem, payload_json: str | None) -> None:
    """把金额/缩略图合并进已有的 result_json，保留其它键。"""
    commerce = _commerce_payload(payload_json)
    if commerce is None:
        return
    try:
        existing = json.loads(work_item.result_json) if work_item.result_json else {}
    except (TypeError, ValueError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing["commerce"] = commerce
    work_item.result_json = _payload(existing)


def _priority(severity: str) -> str:
    return {
        "urgent": "urgent",
        "attention": "attention",
    }.get(severity, "normal")


async def _latest_signal(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    fingerprint: str,
) -> AgentSignal | None:
    return (
        await db.execute(
            select(AgentSignal)
            .where(
                AgentSignal.workspace_id == workspace_id,
                AgentSignal.fingerprint == fingerprint,
            )
            .order_by(desc(AgentSignal.version))
            .limit(1)
        )
    ).scalar_one_or_none()


async def ingest_agent_signal(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None,
    source_type: str,
    source_id: str,
    signal_type: str,
    severity: str,
    title: str,
    summary: str,
    payload: dict,
    fingerprint: str,
    channel_type: str | None = None,
    channel_id: str | None = None,
) -> SignalIngestResult:
    """同一开放指纹只更新证据；已解决后再次出现才创建新版本。"""

    now = datetime.now(timezone.utc)
    latest = await _latest_signal(
        db,
        workspace_id=workspace_id,
        fingerprint=fingerprint,
    )
    if latest is not None and latest.status in {
        "new",
        "grouped",
        "task_created",
    }:
        latest.severity = severity
        latest.observed_at = now
        latest.payload_json = _payload(payload)
        latest.status = "task_created"
        work_item = (
            await db.get(WorkItem, latest.work_item_id)
            if latest.work_item_id
            else None
        )
        if work_item is not None:
            work_item.title = title[:200]
            work_item.summary = summary
            work_item.priority = _priority(severity)
            work_item.source_version = str(latest.version)
            if channel_type is not None:
                work_item.channel_type = channel_type
            if channel_id is not None:
                work_item.channel_id = channel_id
            # 金额和商品图随信号一起刷新，否则订单金额变了界面还是旧数字。
            _attach_commerce(work_item, latest.payload_json)
            work_item.version += 1
        else:
            work_item = await _create_signal_work_item(
                db,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                signal=latest,
                title=title,
                summary=summary,
                channel_type=channel_type,
                channel_id=channel_id,
            )
            latest.work_item_id = work_item.id
        await db.flush()
        return SignalIngestResult(False, latest, work_item)

    version = (latest.version + 1) if latest is not None else 1
    signal = AgentSignal(
        workspace_id=workspace_id,
        source_type=source_type,
        source_id=source_id,
        signal_type=signal_type,
        severity=severity,
        fingerprint=fingerprint,
        version=version,
        observed_at=now,
        payload_json=_payload(payload),
        status="new",
    )
    db.add(signal)
    await db.flush()
    work_item = await _create_signal_work_item(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        signal=signal,
        title=title,
        summary=summary,
        channel_type=channel_type,
        channel_id=channel_id,
    )
    signal.work_item_id = work_item.id
    signal.status = "task_created"
    await db.flush()
    return SignalIngestResult(True, signal, work_item)


async def _create_signal_work_item(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None,
    signal: AgentSignal,
    title: str,
    summary: str,
    channel_type: str | None,
    channel_id: str | None,
) -> WorkItem:
    rule = SIGNAL_WORK_ITEM_RULES.get(
        signal.signal_type,
        {
            "kind": "agent_signal",
            "requires_action": "none",
            "current_step": "Agent 正在处理",
        },
    )
    result: dict = {
        "signal_type": signal.signal_type,
        "source_type": signal.source_type,
        "source_id": signal.source_id,
    }
    commerce = _commerce_payload(signal.payload_json)
    if commerce is not None:
        result["commerce"] = commerce

    return await create_work_item(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        kind=rule["kind"],
        source="integration",
        title=title,
        summary=summary,
        priority=_priority(signal.severity),
        requires_action=rule["requires_action"],
        status=(
            "waiting_user"
            if rule["requires_action"] != "none"
            else "running"
        ),
        current_step=rule["current_step"],
        source_type="agent_signal",
        source_id=str(signal.id),
        source_version=str(signal.version),
        channel_type=channel_type,
        channel_id=channel_id,
        result=result,
    )


async def resolve_agent_signal(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    signal_id: UUID,
    summary: str,
) -> AgentSignal:
    """问题消失后关闭信号和关联工作项，不让旧任务继续占用计划。"""

    signal = (
        await db.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace_id,
                AgentSignal.id == signal_id,
            )
        )
    ).scalar_one_or_none()
    if signal is None:
        raise ValueError("信号不存在")
    signal.status = "resolved"
    signal.resolved_at = datetime.now(timezone.utc)
    if signal.work_item_id:
        work_item = await db.get(WorkItem, signal.work_item_id)
        if work_item is not None:
            work_item.status = "succeeded"
            work_item.requires_action = "none"
            work_item.current_step = "问题已解决"
            work_item.summary = summary
            work_item.version += 1
    await db.flush()
    return signal


async def resolve_latest_signal_by_fingerprint(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    fingerprint: str,
    summary: str,
) -> AgentSignal | None:
    """按业务指纹关闭当前开放信号，找不到时视为已经解决。"""

    signal = await _latest_signal(
        db,
        workspace_id=workspace_id,
        fingerprint=fingerprint,
    )
    if signal is None or signal.status == "resolved":
        return signal
    return await resolve_agent_signal(
        db,
        workspace_id=workspace_id,
        signal_id=signal.id,
        summary=summary,
    )


async def save_integration_cursor(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    channel_id: str,
    resource_type: str,
    cursor_value: str,
    overlap_seconds: int = 300,
) -> IntegrationCursor:
    """保存带重叠窗口的同步游标，重复记录由信号指纹去重。"""

    cursor = (
        await db.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace_id,
                IntegrationCursor.channel_id == channel_id,
                IntegrationCursor.resource_type == resource_type,
            )
        )
    ).scalar_one_or_none()
    if cursor is None:
        cursor = IntegrationCursor(
            workspace_id=workspace_id,
            channel_id=channel_id,
            resource_type=resource_type,
            cursor_value=cursor_value,
            overlap_seconds=max(0, overlap_seconds),
            last_success_at=datetime.now(timezone.utc),
        )
        db.add(cursor)
    else:
        cursor.cursor_value = cursor_value
        cursor.overlap_seconds = max(0, overlap_seconds)
        cursor.last_success_at = datetime.now(timezone.utc)
    await db.flush()
    return cursor
