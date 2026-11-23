"""Temu 商品提交状态追踪、工作项和调度测试。"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_signal import AgentSignal
from app.models.agent_work import WorkItem
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services import provider_config
from app.services.temu_listing_publish import TemuListingPublishService
from app.services.temu_listing_status_sync import (
    interpret_temu_listing_status,
    register_temu_listing_submission,
    sync_all_temu_listing_statuses,
)
from app.services.temu_open_api import TemuOpenApiService
from app.services.scheduler import SchedulerService
from app.services.workspaces import ensure_personal_workspace


async def _context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Status Store",
        external_account_id=f"mall-status-{user.id}",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"status-secret"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "local",
                "api_scope_list": [
                    "bg.local.goods.list.query",
                    "bg.local.goods.publish.status.get",
                ],
            }
        ),
    )
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=uuid4(),
        platform="temu",
        language="en",
        tone="professional",
        status="ready",
        title="Temu Status Product",
        description="Status tracking product.",
        version=1,
        content_hash="b" * 64,
        compliance_status="passed",
    )
    db_session.add_all([connection, listing])
    await db_session.commit()
    await db_session.refresh(connection)
    await db_session.refresh(listing)
    return user, workspace, connection, listing


@pytest.mark.asyncio
async def test_register_temu_submission_is_idempotent(db_session):
    user, workspace, connection, listing = await _context(
        db_session,
        "temu-status-register@example.com",
    )

    first = await register_temu_listing_submission(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        connection_id=connection.id,
        listing_id=listing.id,
        goods_id=9001,
        external_goods_id="external-9001",
        raw_status=2,
        raw_sub_status=5,
    )
    await db_session.commit()
    second = await register_temu_listing_submission(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        connection_id=connection.id,
        listing_id=listing.id,
        goods_id=9001,
        external_goods_id="external-9001",
        raw_status=2,
        raw_sub_status=5,
    )
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    payload = json.loads(signal.payload_json)
    assert first.created is True
    assert second.created is False
    assert signal.signal_type == "temu_listing_processing"
    assert work.kind == "listing_action"
    assert work.status == "running"
    assert payload["goods_id"] == 9001
    assert payload["listing_id"] == str(listing.id)
    assert "status-secret" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_status_sync_updates_signal_without_guessing(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, connection, listing = await _context(
        db_session,
        "temu-status-sync@example.com",
    )
    await register_temu_listing_submission(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        connection_id=connection.id,
        listing_id=listing.id,
        goods_id=9001,
        external_goods_id="external-9001",
        raw_status=2,
        raw_sub_status=5,
    )
    await db_session.commit()
    state = {"status": 2, "sub_status": 5}

    async def fake_statuses(self, *, connection_id, goods_ids):
        assert connection_id == connection.id
        assert goods_ids == [9001]
        return [
            {
                "goods_id": 9001,
                "status": state["status"],
                "sub_status": state["sub_status"],
            }
        ]

    monkeypatch.setattr(
        "app.services.temu_listing_publish."
        "TemuListingPublishService.get_publish_statuses",
        fake_statuses,
    )
    first = await sync_all_temu_listing_statuses(db_session)
    await db_session.commit()
    second = await sync_all_temu_listing_statuses(db_session)
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    payload = json.loads(signal.payload_json)
    assert first["signals_updated"] == 1
    assert second["signals_updated"] == 1
    assert payload["raw_status"] == 2
    assert payload["raw_sub_status"] == 5
    assert payload["observation_count"] == 2
    assert signal.status != "resolved"
    assert work.status == "running"
    assert interpret_temu_listing_status(2, 5) == "processing"


@pytest.mark.asyncio
async def test_confirmed_status_mapping_completes_listing(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, connection, listing = await _context(
        db_session,
        "temu-status-success@example.com",
    )
    await register_temu_listing_submission(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        connection_id=connection.id,
        listing_id=listing.id,
        goods_id=9002,
        external_goods_id="external-9002",
    )
    await db_session.commit()

    async def fake_statuses(self, *, connection_id, goods_ids):
        return [
            {
                "goods_id": 9002,
                "status": 3,
                "sub_status": 7,
            }
        ]

    monkeypatch.setattr(
        "app.services.temu_listing_publish."
        "TemuListingPublishService.get_publish_statuses",
        fake_statuses,
    )
    result = await sync_all_temu_listing_statuses(
        db_session,
        status_map={(3, 7): "succeeded"},
    )
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id
            )
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    await db_session.refresh(listing)
    assert result["signals_resolved"] == 1
    assert signal.status == "resolved"
    assert work.status == "succeeded"
    assert listing.status == "published"
    assert listing.published_at is not None


@pytest.mark.asyncio
async def test_scheduler_registers_temu_listing_status_sync(
    monkeypatch: pytest.MonkeyPatch,
):
    scheduler = SchedulerService()
    monkeypatch.setattr(scheduler.scheduler, "start", lambda: None)

    await scheduler.start()

    job = scheduler.scheduler.get_job("temu_listing_status_sync")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 15 * 60


@pytest.mark.asyncio
async def test_rejected_status_keeps_work_item_for_user(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user, workspace, connection, listing = await _context(
        db_session,
        "temu-status-rejected@example.com",
    )
    await register_temu_listing_submission(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        connection_id=connection.id,
        listing_id=listing.id,
        goods_id=9003,
        external_goods_id="external-9003",
    )
    await db_session.commit()

    async def fake_statuses(self, *, connection_id, goods_ids):
        return [
            {
                "goods_id": 9003,
                "status": 4,
                "sub_status": 9,
            }
        ]

    monkeypatch.setattr(
        "app.services.temu_listing_publish."
        "TemuListingPublishService.get_publish_statuses",
        fake_statuses,
    )
    await sync_all_temu_listing_statuses(
        db_session,
        status_map={(4, 9): "rejected"},
    )
    await db_session.commit()

    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert work.status == "waiting_user"
    assert work.requires_action == "choose"
    assert "需要处理" in work.title


@pytest.mark.asyncio
async def test_status_sync_isolates_one_connection_failure(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    user1, workspace1, connection1, listing1 = await _context(
        db_session,
        "temu-status-fail@example.com",
    )
    user2, workspace2, connection2, listing2 = await _context(
        db_session,
        "temu-status-ok@example.com",
    )
    await register_temu_listing_submission(
        db_session,
        workspace_id=workspace1.id,
        actor_user_id=user1.id,
        connection_id=connection1.id,
        listing_id=listing1.id,
        goods_id=9004,
        external_goods_id="external-9004",
    )
    await register_temu_listing_submission(
        db_session,
        workspace_id=workspace2.id,
        actor_user_id=user2.id,
        connection_id=connection2.id,
        listing_id=listing2.id,
        goods_id=9005,
        external_goods_id="external-9005",
    )
    await db_session.commit()

    async def fake_statuses(self, *, connection_id, goods_ids):
        if connection_id == connection1.id:
            raise ValueError("Temu 状态接口限流")
        return [
            {
                "goods_id": 9005,
                "status": 2,
                "sub_status": 5,
            }
        ]

    monkeypatch.setattr(
        "app.services.temu_listing_publish."
        "TemuListingPublishService.get_publish_statuses",
        fake_statuses,
    )
    result = await sync_all_temu_listing_statuses(db_session)
    await db_session.commit()

    assert result["failure_count"] == 1
    assert result["signals_updated"] == 1
    failed_signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace1.id
            )
        )
    ).scalar_one()
    succeeded_signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace2.id
            )
        )
    ).scalar_one()
    assert json.loads(failed_signal.payload_json).get(
        "observation_count"
    ) is None
    assert json.loads(succeeded_signal.payload_json)[
        "observation_count"
    ] == 1


@pytest.mark.asyncio
async def test_publish_status_service_uses_batch_goods_ids(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_KEY",
        "temu-app-key",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_SECRET",
        "temu-app-secret",
        raising=False,
    )
    provider_config.clear_cache()
    user, _workspace, connection, _listing = await _context(
        db_session,
        "temu-status-service@example.com",
    )
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.update(body)
        return httpx.Response(
            200,
            json={
                "success": True,
                "errorCode": 1000000,
                "result": {
                    "goodsPublishStatusList": [
                        {
                            "goodsId": 9001,
                            "status": 2,
                            "subStatus": 5,
                        },
                        {
                            "goodsId": 9002,
                            "status": 3,
                            "subStatus": 7,
                        },
                    ]
                },
            },
        )

    service = TemuListingPublishService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    rows = await service.get_publish_statuses(
        connection_id=connection.id,
        goods_ids=[9002, 9001],
    )

    assert captured["type"] == "bg.local.goods.publish.status.get"
    assert captured["goodsIdList"] == [9001, 9002]
    assert rows == [
        {"goods_id": 9001, "status": 2, "sub_status": 5},
        {"goods_id": 9002, "status": 3, "sub_status": 7},
    ]
    assert "status-secret" not in json.dumps(rows)


@pytest.mark.asyncio
async def test_publish_status_service_falls_back_to_goods_list(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_KEY",
        "temu-app-key",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_SECRET",
        "temu-app-secret",
        raising=False,
    )
    provider_config.clear_cache()
    user, _workspace, connection, _listing = await _context(
        db_session,
        "temu-status-fallback@example.com",
    )
    connection.metadata_json = json.dumps(
        {
            "store_type": "local",
            "api_scope_list": ["bg.local.goods.list.query"],
        }
    )
    await db_session.commit()
    request_types = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_types.append(body["type"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "errorCode": 1000000,
                "result": {
                    "total": 1,
                    "goodsList": [
                        {
                            "goodsId": 9001,
                            "outGoodsSn": "external-9001",
                            "status4VO": 2,
                            "subStatus4VO": 5,
                        }
                    ],
                },
            },
        )

    service = TemuListingPublishService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    rows = await service.get_publish_statuses(
        connection_id=connection.id,
        goods_ids=[9001],
    )

    assert request_types == ["bg.local.goods.list.query"]
    assert rows == [
        {"goods_id": 9001, "status": 2, "sub_status": 5}
    ]
