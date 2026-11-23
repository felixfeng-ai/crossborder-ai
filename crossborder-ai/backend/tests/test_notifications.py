"""移动推送待发、设备与隐私边界测试。"""

import json

import pytest
from sqlalchemy import select

from app.models.notification import MobileDevice, NotificationDelivery, NotificationOutbox
from app.models.user import User
from app.services.notifications import (
    NotificationMessage,
    create_notification,
    dispatch_notification_outbox,
    register_mobile_device,
    update_notification_preference,
)
from app.services.work_items import create_work_item
from app.services.workspaces import ensure_personal_workspace


class FakePushSender:
    def __init__(self, statuses=None):
        self.statuses = statuses or {}
        self.messages = []

    async def send(self, messages: list[NotificationMessage]):
        self.messages.extend(messages)
        return [
            self.statuses.get(
                message.to,
                {"status": "ok", "id": f"ticket-{index}"},
            )
            for index, message in enumerate(messages, start=1)
        ]


async def _user_workspace(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    return user, workspace


@pytest.mark.asyncio
async def test_notification_is_idempotent_and_push_payload_has_no_sensitive_data(
    db_session,
):
    user, workspace = await _user_workspace(
        db_session,
        "notification-private@example.com",
    )
    device = await register_mobile_device(
        db_session,
        user_id=user.id,
        expo_push_token="ExponentPushToken[private-device]",
        platform="ios",
        device_name="iPhone",
    )
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="order_exception",
        source="integration",
        title="订单异常",
        summary="买家地址和金额不应进入推送。",
        requires_action="confirm",
    )
    first = await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        work_item_id=item.id,
        notification_type="needs_action",
        title="有 1 件事需要你决定",
        body="点击进入 VeyaShip 处理。",
        deep_link=f"/t/{item.id}?workspaceId={workspace.id}",
        dedupe_key=f"work-item:{item.id}:needs-action",
    )
    second = await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        work_item_id=item.id,
        notification_type="needs_action",
        title="有 1 件事需要你决定",
        body="点击进入 VeyaShip 处理。",
        deep_link=f"/t/{item.id}?workspaceId={workspace.id}",
        dedupe_key=f"work-item:{item.id}:needs-action",
    )
    await db_session.commit()
    assert first.id == second.id
    assert (await db_session.get(MobileDevice, device.id)).status == "active"

    sender = FakePushSender()
    result = await dispatch_notification_outbox(db_session, sender=sender)
    await db_session.commit()

    assert result["sent"] == 1
    assert len(sender.messages) == 1
    payload = json.dumps(sender.messages[0].to_dict(), ensure_ascii=False)
    assert "买家地址" not in payload
    assert "金额" not in payload
    assert str(item.id) in payload
    delivery = (
        await db_session.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == first.id,
            )
        )
    ).scalar_one()
    assert delivery.status == "sent"


@pytest.mark.asyncio
async def test_invalid_push_token_is_disabled_and_marked_failed(db_session):
    user, workspace = await _user_workspace(
        db_session,
        "notification-invalid@example.com",
    )
    device = await register_mobile_device(
        db_session,
        user_id=user.id,
        expo_push_token="ExponentPushToken[invalid-device]",
        platform="android",
        device_name="Pixel",
    )
    notification = await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        notification_type="action_failed",
        title="有一项操作失败",
        body="点击查看恢复方式。",
        deep_link="/activity",
        dedupe_key="action-failed:1",
    )
    await db_session.commit()
    sender = FakePushSender(
        {
            device.expo_push_token: {
                "status": "error",
                "details": {"error": "DeviceNotRegistered"},
                "message": "Device is not registered",
            }
        }
    )

    result = await dispatch_notification_outbox(db_session, sender=sender)
    await db_session.commit()
    await db_session.refresh(device)
    delivery = (
        await db_session.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id,
            )
        )
    ).scalar_one()

    assert result["failed"] == 1
    assert device.status == "invalid"
    assert delivery.status == "failed"
    assert delivery.error_code == "DeviceNotRegistered"


@pytest.mark.asyncio
async def test_mobile_notification_list_exposes_safe_fields_only(
    client,
    db_session,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "notification-api@example.com",
            "username": "notification-api",
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "notification-api@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        kind="customer_reply",
        source="integration",
        title="客户问题",
        summary="客户原文不应出现在推送列表。",
        requires_action="confirm",
    )
    await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        work_item_id=item.id,
        notification_type="needs_action",
        title="有 1 件事需要你决定",
        body="点击进入 VeyaShip 处理。",
        deep_link=f"/t/{item.id}?workspaceId={workspace.id}",
        dedupe_key="notification-api:1",
    )
    await db_session.commit()

    listing = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/notifications",
        headers=headers,
    )

    assert listing.status_code == 200
    assert len(listing.json()) >= 1
    wanted_link = f"/t/{item.id}?workspaceId={workspace.id}"
    payload = next(
        entry
        for entry in listing.json()
        if entry["deep_link"] == wanted_link
    )
    assert payload["deep_link"].endswith(f"/t/{item.id}?workspaceId={workspace.id}")
    assert "客户原文" not in listing.text
    assert "客户问题" not in listing.text


@pytest.mark.asyncio
async def test_mobile_single_notification_can_be_marked_read(
    client,
    db_session,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "notification-single-read@example.com",
            "username": "notification-single-read",
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(
                User.email == "notification-single-read@example.com"
            )
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    first = await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        notification_type="needs_action",
        title="第一条通知",
        body="点击处理。",
        deep_link="/activity",
        dedupe_key="single-read:1",
    )
    second = await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        notification_type="needs_action",
        title="第二条通知",
        body="点击处理。",
        deep_link="/activity",
        dedupe_key="single-read:2",
    )
    await db_session.commit()

    marked = await client.post(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/notifications/{first.id}/read"
        ),
        headers=headers,
    )
    listing = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/notifications",
        headers=headers,
    )

    assert marked.status_code == 200
    assert marked.json()["id"] == str(first.id)
    by_id = {entry["id"]: entry for entry in listing.json()}
    assert by_id[str(first.id)]["read_at"] is not None
    assert by_id[str(second.id)]["read_at"] is None


@pytest.mark.asyncio
async def test_notification_preferences_can_disable_noise(db_session):
    user, workspace = await _user_workspace(
        db_session,
        "notification-preference@example.com",
    )
    await register_mobile_device(
        db_session,
        user_id=user.id,
        expo_push_token="ExponentPushToken[preference-device]",
        platform="ios",
    )
    await update_notification_preference(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        values={"day_closeout": False},
    )
    notification = await create_notification(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        notification_type="day_closeout",
        title="今日日结已生成",
        body="点击查看。",
        deep_link="/plan",
        dedupe_key="preference-closeout-1",
    )
    await db_session.commit()
    sender = FakePushSender()

    result = await dispatch_notification_outbox(db_session, sender=sender)
    await db_session.commit()
    await db_session.refresh(notification)

    assert result["checked"] == 1
    assert sender.messages == []
    assert notification.status == "cancelled"
    assert notification.error_code == "preference_disabled"


@pytest.mark.asyncio
async def test_mark_all_notifications_read(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "notification-readall@example.com",
            "username": "notification-readall",
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(
            select(User).where(User.email == "notification-readall@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    for index in (1, 2):
        await create_notification(
            db_session,
            workspace_id=workspace.id,
            user_id=user.id,
            notification_type="needs_action",
            title=f"提醒 {index}",
            body="点击处理。",
            deep_link="/activity",
            dedupe_key=f"read-all-{index}",
        )
    await db_session.commit()

    marked = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/notifications/read-all",
        headers=headers,
    )

    assert marked.status_code == 200
    assert marked.json()["marked"] >= 2

    listing = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/notifications",
        headers=headers,
    )
    assert listing.status_code == 200
    assert all(entry["read_at"] for entry in listing.json())
