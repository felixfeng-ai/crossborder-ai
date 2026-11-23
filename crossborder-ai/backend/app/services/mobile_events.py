"""移动端实时事件流。

事件只承载变更和必要标识，客户端收到后重新拉取权威详情，避免实时通道成为
第二套业务数据接口。
"""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_work import WorkItemEvent


EVENT_NAMES = {
    "work_item.created": "work_item.updated",
    "work_item.command.accepted": "work_item.updated",
    "work_item.agent_task.succeeded": "work_item.updated",
    "work_item.agent_task.failed": "work_item.updated",
    "action_run.planned": "action.waiting",
    "action_run.confirmed": "action.waiting",
    "action_run.retry_queued": "action.waiting",
    "action_run.started": "action.started",
    "action_run.awaiting_result": "action.waiting",
    "action_run.succeeded": "action.completed",
    "action_run.blocked": "action.failed",
    "action_run.retryable_failed": "action.failed",
}


def _payload(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def mobile_event_package(event: WorkItemEvent) -> dict:
    """把数据库事件转换成稳定的移动端事件包。"""

    payload = _payload(event.payload_json)
    return {
        "event_id": str(event.id),
        "type": EVENT_NAMES.get(event.event_type, "work_item.updated"),
        "schema_version": "1",
        "workspace_id": str(event.workspace_id),
        "work_item_id": str(event.work_item_id),
        "agent_turn_id": payload.get("agent_turn_id"),
        "action_run_id": payload.get("action_run_id"),
        "occurred_at": event.created_at.isoformat(),
        "data": {
            "event_type": event.event_type,
            **payload,
        },
    }


def serialize_sse(event: WorkItemEvent) -> str:
    """按 SSE 规范输出事件，断线后可以用 Last-Event-ID 续传。"""

    package = mobile_event_package(event)
    return (
        f"id: {package['event_id']}\n"
        f"event: {package['type']}\n"
        f"data: {json.dumps(package, ensure_ascii=False)}\n\n"
    )


async def stream_workspace_events(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: int,
    once: bool = False,
    max_polls: int | None = None,
) -> AsyncIterator[str]:
    """持续读取工作区事件。

    `once` 和 `max_polls` 主要供自动化测试使用；正式连接不带这两个参数，
    客户端断开后服务端停止循环。
    """

    polls = 0
    while True:
        events = (
            await db.execute(
                select(WorkItemEvent)
                .where(
                    WorkItemEvent.workspace_id == workspace_id,
                    WorkItemEvent.id > cursor,
                )
                .order_by(WorkItemEvent.id)
                .limit(100)
            )
        ).scalars().all()
        if events:
            for event in events:
                cursor = event.id
                yield serialize_sse(event)
            if once:
                return
            continue

        if once:
            return
        polls += 1
        if max_polls is not None and polls >= max_polls:
            return
        yield ": ping\n\n"
        await asyncio.sleep(1)
