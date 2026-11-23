"""Webhook 原始事件、Shopify 验签和按渠道同步租约。"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration_event import IntegrationEvent, IntegrationLease
from app.models.workspace import Workspace
from app.services.agent_signals import (
    ingest_agent_signal,
    resolve_latest_signal_by_fingerprint,
)


async def record_integration_event(
    db: AsyncSession,
    *,
    workspace_id,
    channel_id: str,
    provider: str,
    external_event_id: str,
    event_type: str,
    external_resource_id: str | None,
    payload: dict,
    fingerprint: str,
    signature_verified: bool,
) -> tuple[IntegrationEvent, bool]:
    """原始事件按平台事件编号幂等落库，重复事件不重复归一化。"""

    existing = (
        await db.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.workspace_id == workspace_id,
                IntegrationEvent.provider == provider,
                IntegrationEvent.external_event_id == external_event_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    event = IntegrationEvent(
        workspace_id=workspace_id,
        channel_id=channel_id,
        provider=provider,
        external_event_id=external_event_id,
        event_type=event_type,
        external_resource_id=external_resource_id,
        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        fingerprint=fingerprint,
        signature_verified=signature_verified,
        status="received",
        attempts=0,
        max_attempts=5,
    )
    db.add(event)
    await db.flush()
    return event, True


def verify_shopify_hmac(
    *,
    secret: str | None,
    body: bytes,
    signature: str | None,
) -> bool:
    """校验 Shopify `X-Shopify-Hmac-Sha256`。"""

    if not secret or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def claim_integration_lease(
    db: AsyncSession,
    *,
    workspace_id,
    channel_id: str,
    resource_type: str,
    owner_token: str,
    ttl_seconds: int = 300,
) -> IntegrationLease | None:
    """抢占渠道资源租约；未过期时其他 worker 不能执行。"""

    now = datetime.now(timezone.utc)
    lease = (
        await db.execute(
            select(IntegrationLease)
            .where(
                IntegrationLease.workspace_id == workspace_id,
                IntegrationLease.channel_id == channel_id,
                IntegrationLease.resource_type == resource_type,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if lease is not None and _utc(lease.locked_until) > now:
        return None
    if lease is None:
        lease = IntegrationLease(
            workspace_id=workspace_id,
            channel_id=channel_id,
            resource_type=resource_type,
            owner_token=owner_token,
            locked_until=now + timedelta(seconds=max(1, ttl_seconds)),
        )
        db.add(lease)
    else:
        lease.owner_token = owner_token
        lease.locked_until = now + timedelta(seconds=max(1, ttl_seconds))
    await db.flush()
    return lease


async def release_integration_lease(
    db: AsyncSession,
    *,
    workspace_id,
    channel_id: str,
    resource_type: str,
    owner_token: str,
) -> bool:
    """只允许租约持有者释放；过期回收由下一次 claim 完成。"""

    lease = (
        await db.execute(
            select(IntegrationLease).where(
                IntegrationLease.workspace_id == workspace_id,
                IntegrationLease.channel_id == channel_id,
                IntegrationLease.resource_type == resource_type,
                IntegrationLease.owner_token == owner_token,
            )
        )
    ).scalar_one_or_none()
    if lease is None:
        return False
    await db.delete(lease)
    await db.flush()
    return True


def _event_payload(event: IntegrationEvent) -> dict:
    try:
        payload = json.loads(event.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        raise ValueError("payload_invalid")
    if not isinstance(payload, dict):
        raise ValueError("payload_invalid")
    return payload


def _order_age_hours(order: dict) -> int:
    value = str(order.get("created_at") or "").replace("Z", "+00:00")
    try:
        created_at = datetime.fromisoformat(value)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return max(
            0,
            int(
                (
                    datetime.now(timezone.utc) - created_at
                ).total_seconds()
                // 3600
            ),
        )
    except (TypeError, ValueError):
        return 0


async def process_pending_integration_events(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> dict:
    """消费收到的原始事件；处理失败保留错误，不阻塞其他事件。"""

    events = (
        await db.execute(
            select(IntegrationEvent)
            .where(
                IntegrationEvent.status.in_(
                    ["received", "retryable_failed"]
                ),
                (IntegrationEvent.available_at.is_(None))
                | (IntegrationEvent.available_at <= datetime.now(timezone.utc)),
            )
            .order_by(IntegrationEvent.received_at, IntegrationEvent.id)
            .limit(max(1, limit))
        )
    ).scalars().all()
    normalized = 0
    failed = 0
    ignored = 0
    for event in events:
        event.attempts += 1
        try:
            payload = _event_payload(event)
            if event.provider != "shopify" or not event.event_type.startswith(
                "orders/"
            ):
                event.status = "ignored"
                event.processed_at = datetime.now(timezone.utc)
                ignored += 1
                continue
            order = payload.get("order")
            if not isinstance(order, dict):
                order = payload
            workspace = await db.get(Workspace, event.workspace_id)
            if workspace is None:
                raise ValueError("workspace_missing")
            order_id = str(
                order.get("id")
                or event.external_resource_id
                or ""
            ).strip()
            if not order_id:
                raise ValueError("order_id_missing")
            fingerprint = (
                f"shopify-order:{event.channel_id}:{order_id}:unfulfilled"
            )
            closed = (
                order.get("fulfillment_status") == "fulfilled"
                or bool(order.get("cancelled_at"))
                or event.event_type
                in {"orders/cancelled", "orders/fulfilled"}
            )
            if closed:
                await resolve_latest_signal_by_fingerprint(
                    db,
                    workspace_id=event.workspace_id,
                    fingerprint=fingerprint,
                    summary="Shopify Webhook 显示订单已完成或取消。",
                )
            else:
                age_hours = _order_age_hours(order)
                await ingest_agent_signal(
                    db,
                    workspace_id=event.workspace_id,
                    actor_user_id=workspace.owner_user_id,
                    source_type="shopify_order",
                    source_id=order_id,
                    signal_type="order_awaiting_shipment",
                    severity=(
                        "urgent"
                        if age_hours >= 48
                        else "attention"
                        if age_hours >= 24
                        else "normal"
                    ),
                    title="有一笔订单等待发货",
                    summary=(
                        "订单等待时间较长，建议今天完成履约。"
                        if age_hours >= 24
                        else "Agent 正在关注订单履约状态。"
                    ),
                    payload={
                        "order_id": order_id,
                        "order_name": order.get("name"),
                        "age_hours": age_hours,
                        "source_event_id": event.external_event_id,
                    },
                    fingerprint=fingerprint,
                )
            event.status = "normalized"
            event.processed_at = datetime.now(timezone.utc)
            event.error_code = None
            event.available_at = None
            normalized += 1
        except ValueError as exc:
            event.error_code = str(exc)[:80]
            if event.attempts >= event.max_attempts:
                event.status = "dead_letter"
            else:
                event.status = "retryable_failed"
                event.available_at = datetime.now(timezone.utc) + timedelta(
                    seconds=min(300, 5 * 2 ** (event.attempts - 1))
                )
            failed += 1
        except Exception as exc:
            if event.attempts >= event.max_attempts:
                event.status = "dead_letter"
            else:
                event.status = "retryable_failed"
                event.available_at = datetime.now(timezone.utc) + timedelta(
                    seconds=min(300, 5 * 2 ** (event.attempts - 1))
                )
            event.error_code = "normalize_failed"
            event.payload_json = (
                event.payload_json or ""
            ) + f"\n# error: {str(exc)[:200]}"
            failed += 1
    await db.flush()
    return {
        "checked": len(events),
        "processed": normalized + failed,
        "normalized": normalized,
        "failed": failed,
        "ignored": ignored,
    }


async def retry_integration_event(
    db: AsyncSession,
    *,
    workspace_id,
    event_id,
) -> IntegrationEvent:
    """人工重放死信事件；保留原始 payload 和事件编号。"""

    event = (
        await db.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.workspace_id == workspace_id,
                IntegrationEvent.id == event_id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise ValueError("事件不存在")
    if event.status not in {"dead_letter", "retryable_failed"}:
        raise ValueError("当前事件不需要重放")
    event.status = "received"
    event.attempts = 0
    event.error_code = None
    event.available_at = datetime.now(timezone.utc)
    event.processed_at = None
    await db.flush()
    return event
