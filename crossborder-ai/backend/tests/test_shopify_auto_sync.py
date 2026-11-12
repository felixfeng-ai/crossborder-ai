"""Shopify 店铺自动同步的失败隔离测试。"""

import uuid

import pytest

from app.core.crypto import encrypt_value
from app.models.automation_preference import AutomationPreference
from app.models.shopify_channel import ShopifyChannel
from app.models.user import User
from app.services.scheduler import SchedulerService
from app.services.shopify_operations_sync import (
    ShopifyOperationsSyncError,
    sync_all_shopify_operations,
)


@pytest.mark.asyncio
async def test_sync_all_active_shopify_channels_isolates_failures(
    db_session,
    monkeypatch,
):
    """一个店铺失败时仍应继续同步其他启用店铺。"""

    async def create_user(label: str) -> User:
        user = User(
            email=f"auto-sync-{label}-{uuid.uuid4().hex[:8]}@test.com",
            username=f"auto-sync-{label}",
            password_hash="x",
            plan="standard",
        )
        db_session.add(user)
        await db_session.flush()
        return user

    success_user = await create_user("success")
    failed_user = await create_user("failed")
    inactive_user = await create_user("inactive")
    success_channel = ShopifyChannel(
        user_id=success_user.id,
        shop_name="auto-sync-success",
        shop_domain="auto-sync-success.myshopify.com",
        access_token=encrypt_value("shpat_success"),
        is_active=True,
    )
    failed_channel = ShopifyChannel(
        user_id=failed_user.id,
        shop_name="auto-sync-failed",
        shop_domain="auto-sync-failed.myshopify.com",
        access_token=encrypt_value("shpat_failed"),
        is_active=True,
    )
    inactive_channel = ShopifyChannel(
        user_id=inactive_user.id,
        shop_name="auto-sync-inactive",
        shop_domain="auto-sync-inactive.myshopify.com",
        access_token=encrypt_value("shpat_inactive"),
        is_active=False,
    )
    db_session.add_all([success_channel, failed_channel, inactive_channel])
    await db_session.commit()
    success_channel_id = success_channel.id
    failed_channel_id = failed_channel.id
    inactive_channel_id = inactive_channel.id

    called_channel_ids: list[uuid.UUID] = []

    async def fake_sync(db, *, user, channel, days=30):
        assert db is db_session
        called_channel_ids.append(channel.id)
        if channel.id == failed_channel_id:
            raise ShopifyOperationsSyncError("模拟 Shopify 请求失败")
        return {
            "orders_scanned": 3,
            "campaign_performance_updates": 1,
        }

    monkeypatch.setattr(
        "app.services.shopify_operations_sync.sync_shopify_operations",
        fake_sync,
    )

    result = await sync_all_shopify_operations(db_session, days=14)

    assert set(called_channel_ids) == {success_channel_id, failed_channel_id}
    assert inactive_channel_id not in called_channel_ids
    assert result["channels_scanned"] == 2
    assert result["channels_succeeded"] == 1
    assert result["channels_failed"] == 1
    assert result["orders_scanned"] == 3
    assert result["campaign_performance_updates"] == 1
    assert result["failures"][0]["channel_id"] == str(failed_channel_id)


@pytest.mark.asyncio
async def test_scheduler_registers_shopify_auto_sync_job():
    """生产调度器必须注册 Shopify 自动同步任务。"""

    service = SchedulerService()
    job_ids: list[str] = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, *, id, replace_existing):
            job_ids.append(id)

        def start(self):
            self.running = True

    service.scheduler = FakeScheduler()
    await service.start()

    assert "shopify_operations_sync" in job_ids


@pytest.mark.asyncio
async def test_sync_all_skips_shopify_when_user_turned_off(
    db_session,
    monkeypatch,
):
    user = User(
        email=f"auto-sync-off-{uuid.uuid4().hex[:8]}@test.com",
        username="auto-sync-off",
        password_hash="x",
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()
    channel = ShopifyChannel(
        user_id=user.id,
        shop_name="auto-sync-off",
        shop_domain="auto-sync-off.myshopify.com",
        access_token=encrypt_value("shpat_off"),
        is_active=True,
    )
    db_session.add(channel)
    db_session.add(
        AutomationPreference(
            user_id=user.id,
            shopify_auto_sync=False,
        )
    )
    await db_session.commit()

    async def should_not_run(*args, **kwargs):
        raise AssertionError("关闭 Shopify 自动同步后不应调用真实同步")

    monkeypatch.setattr(
        "app.services.shopify_operations_sync.sync_shopify_operations",
        should_not_run,
    )

    result = await sync_all_shopify_operations(db_session)

    assert result["channels_scanned"] == 1
    assert result["channels_skipped"] == 1
    assert result["channels_succeeded"] == 0
