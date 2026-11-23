"""移动推送设备注册、通知待发和投递执行。"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    MobileDevice,
    NotificationDelivery,
    NotificationOutbox,
    NotificationPreference,
)


@dataclass
class NotificationMessage:
    """发送给 Expo Push 服务的最小隐私安全载荷。"""

    to: str
    title: str
    body: str
    data: dict = field(default_factory=dict)
    sound: str = "default"
    channel_id: str = "default"

    def to_dict(self) -> dict:
        return {
            "to": self.to,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "sound": self.sound,
            "channelId": self.channel_id,
        }


class PushSender(Protocol):
    async def send(self, messages: list[NotificationMessage]) -> list[dict]:
        """返回与输入消息一一对应的 Expo Push 响应。"""


class ExpoPushSender:
    """Expo Push 服务发送器。"""

    async def send(self, messages: list[NotificationMessage]) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=[message.to_dict() for message in messages],
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Expo Push 请求失败：{response.text[:200]}")
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else payload
        return data if isinstance(data, list) else []


async def register_mobile_device(
    db: AsyncSession,
    *,
    user_id: UUID,
    expo_push_token: str,
    platform: str,
    device_name: str | None = None,
) -> MobileDevice:
    token = expo_push_token.strip()
    if not token.startswith("ExponentPushToken[") and not token.startswith(
        "ExpoPushToken["
    ):
        raise ValueError("推送令牌格式不正确")
    device = (
        await db.execute(
            select(MobileDevice).where(
                MobileDevice.expo_push_token == token,
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if device is None:
        device = MobileDevice(
            user_id=user_id,
            expo_push_token=token,
            platform=platform,
            device_name=device_name,
            status="active",
            last_seen_at=now,
        )
        db.add(device)
    else:
        device.user_id = user_id
        device.platform = platform
        device.device_name = device_name
        device.status = "active"
        device.last_seen_at = now
    await db.flush()
    return device


async def get_notification_preference(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID,
) -> NotificationPreference:
    preference = (
        await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if preference is None:
        preference = NotificationPreference(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        db.add(preference)
        await db.flush()
    return preference


async def update_notification_preference(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: UUID,
    values: dict,
) -> NotificationPreference:
    preference = await get_notification_preference(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    for field in (
        "morning_brief",
        "day_closeout",
        "needs_action",
        "action_failed",
        "authorization_expired",
        "quiet_start_hour",
        "quiet_end_hour",
        "timezone",
    ):
        if field in values:
            setattr(preference, field, values[field])
    await db.flush()
    return preference


def _notification_enabled(
    preference: NotificationPreference,
    notification_type: str,
) -> bool:
    return {
        "morning_brief": preference.morning_brief,
        "day_closeout": preference.day_closeout,
        "needs_action": preference.needs_action,
        "action_failed": preference.action_failed,
        "authorization_expired": preference.authorization_expired,
    }.get(notification_type, True)


def _next_quiet_end(
    preference: NotificationPreference,
    now: datetime,
) -> datetime | None:
    start = preference.quiet_start_hour
    end = preference.quiet_end_hour
    if start is None or end is None or start == end:
        return None
    try:
        local_now = now.astimezone(ZoneInfo(preference.timezone))
    except ZoneInfoNotFoundError:
        local_now = now
    hour = local_now.hour
    quiet = (
        start <= hour < end
        if start < end
        else hour >= start or hour < end
    )
    if not quiet:
        return None
    end_time = local_now.replace(
        hour=end,
        minute=0,
        second=0,
        microsecond=0,
    )
    if end_time <= local_now:
        end_time += timedelta(days=1)
    return end_time.astimezone(timezone.utc)


async def create_notification(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    notification_type: str,
    title: str,
    body: str,
    deep_link: str,
    dedupe_key: str,
    work_item_id: UUID | None = None,
    available_at: datetime | None = None,
) -> NotificationOutbox:
    existing = (
        await db.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.workspace_id == workspace_id,
                NotificationOutbox.user_id == user_id,
                NotificationOutbox.dedupe_key == dedupe_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    notification = NotificationOutbox(
        workspace_id=workspace_id,
        user_id=user_id,
        work_item_id=work_item_id,
        notification_type=notification_type,
        title=title[:200],
        body=body[:500],
        deep_link=deep_link[:1000],
        dedupe_key=dedupe_key[:160],
        status="pending",
        available_at=available_at,
    )
    db.add(notification)
    await db.flush()
    return notification


async def _upsert_delivery(
    db: AsyncSession,
    *,
    notification_id: UUID,
    device_id: UUID,
    status: str,
    attempts: int = 1,
    provider_message_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> NotificationDelivery:
    delivery = (
        await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification_id,
                NotificationDelivery.device_id == device_id,
            )
        )
    ).scalar_one_or_none()
    if delivery is None:
        delivery = NotificationDelivery(
            notification_id=notification_id,
            device_id=device_id,
        )
        db.add(delivery)
    delivery.status = status
    delivery.attempts = (delivery.attempts or 0) + attempts
    delivery.provider_message_id = provider_message_id
    delivery.error_code = error_code
    delivery.error_message = error_message
    return delivery


def _message(notification: NotificationOutbox, token: str) -> NotificationMessage:
    """推送只携带路由所需标识，业务详情由登录后的 App 拉取。"""

    data = {
        "notification_id": str(notification.id),
        "workspace_id": str(notification.workspace_id),
        "work_item_id": (
            str(notification.work_item_id)
            if notification.work_item_id
            else None
        ),
        "type": notification.notification_type,
        "deep_link": notification.deep_link,
    }
    return NotificationMessage(
        to=token,
        title=notification.title,
        body=notification.body,
        data=data,
    )


async def dispatch_notification_outbox(
    db: AsyncSession,
    *,
    sender: PushSender | None = None,
    limit: int = 50,
) -> dict:
    now = datetime.now(timezone.utc)
    notifications = (
        await db.execute(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status.in_(["pending", "failed"]),
                (NotificationOutbox.available_at.is_(None))
                | (NotificationOutbox.available_at <= now),
            )
            .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
            .limit(max(1, limit))
        )
    ).scalars().all()
    sender = sender or ExpoPushSender()
    sent = 0
    failed = 0

    for notification in notifications:
        preference = await get_notification_preference(
            db,
            user_id=notification.user_id,
            workspace_id=notification.workspace_id,
        )
        if not _notification_enabled(
            preference,
            notification.notification_type,
        ):
            notification.status = "cancelled"
            notification.error_code = "preference_disabled"
            continue
        quiet_until = (
            None
            if notification.notification_type
            in {"action_failed", "authorization_expired"}
            else _next_quiet_end(preference, now)
        )
        if quiet_until is not None:
            notification.available_at = quiet_until
            continue

        devices = (
            await db.execute(
                select(MobileDevice).where(
                    MobileDevice.user_id == notification.user_id,
                    MobileDevice.status == "active",
                )
            )
        ).scalars().all()
        notification.attempts += 1
        if not devices:
            # 没有设备仍然保留站内通知，不把 outbox 永远卡在 pending。
            notification.status = "sent"
            notification.sent_at = now
            notification.error_code = "no_devices"
            sent += 1
            continue

        messages = [
            _message(notification, device.expo_push_token)
            for device in devices
        ]
        try:
            responses = await sender.send(messages)
        except Exception as exc:
            notification.status = "failed"
            notification.error_code = "provider_error"
            notification.available_at = now
            failed += 1
            for device in devices:
                await _upsert_delivery(
                    db,
                    notification_id=notification.id,
                    device_id=device.id,
                    status="failed",
                    error_code="provider_error",
                    error_message=str(exc)[:500],
                )
            continue

        successful = 0
        for index, device in enumerate(devices):
            response = responses[index] if index < len(responses) else {}
            if response.get("status") == "ok":
                successful += 1
                await _upsert_delivery(
                    db,
                    notification_id=notification.id,
                    device_id=device.id,
                    status="sent",
                    provider_message_id=response.get("id"),
                )
                continue
            error = response.get("details") or {}
            error_code = str(
                error.get("error")
                or response.get("error")
                or "push_failed"
            )[:80]
            if error_code == "DeviceNotRegistered":
                device.status = "invalid"
            await _upsert_delivery(
                db,
                notification_id=notification.id,
                device_id=device.id,
                status="failed",
                error_code=error_code,
                error_message=str(response.get("message") or "")[:500],
            )
        if successful:
            notification.status = "sent"
            notification.sent_at = now
            sent += 1
        else:
            notification.status = "failed"
            notification.error_code = "all_devices_failed"
            failed += 1
    await db.flush()
    return {
        "checked": len(notifications),
        "sent": sent,
        "failed": failed,
    }
