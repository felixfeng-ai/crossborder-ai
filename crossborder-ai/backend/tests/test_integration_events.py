"""Webhook 原始事件去重、验签和渠道租约测试。"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.integration_event import IntegrationEvent, IntegrationLease
from app.models.shopify_channel import ShopifyChannel
from app.models.agent_signal import AgentSignal
from app.models.agent_work import WorkItem
from app.models.user import User
from app.services.integration_events import (
    claim_integration_lease,
    record_integration_event,
    release_integration_lease,
    verify_shopify_hmac,
    process_pending_integration_events,
    retry_integration_event,
)
from app.services.workspaces import ensure_personal_workspace


async def _workspace(db_session, email: str):
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
async def test_webhook_event_is_deduplicated_by_external_event_id(db_session):
    _user, workspace = await _workspace(
        db_session,
        "event-dedupe@example.com",
    )
    first, created_first = await record_integration_event(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        provider="shopify",
        external_event_id="event-1001",
        event_type="orders/create",
        external_resource_id="order-1001",
        payload={"id": 1001},
        fingerprint="shopify:event:event-1001",
        signature_verified=True,
    )
    second, created_second = await record_integration_event(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        provider="shopify",
        external_event_id="event-1001",
        event_type="orders/create",
        external_resource_id="order-1001",
        payload={"id": 1001, "duplicate": True},
        fingerprint="shopify:event:event-1001",
        signature_verified=True,
    )
    await db_session.commit()

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert (
        await db_session.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.workspace_id == workspace.id
            )
        )
    ).scalar_one().status == "received"


@pytest.mark.asyncio
async def test_shopify_hmac_verification_accepts_valid_and_rejects_invalid():
    body = b'{"id":1001}'
    secret = "shopify-secret"
    digest = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    assert verify_shopify_hmac(
        secret=secret,
        body=body,
        signature=digest,
    ) is True
    assert verify_shopify_hmac(
        secret=secret,
        body=body,
        signature="invalid",
    ) is False
    assert verify_shopify_hmac(
        secret=None,
        body=body,
        signature=digest,
    ) is False


@pytest.mark.asyncio
async def test_integration_lease_prevents_parallel_workers(db_session):
    _user, workspace = await _workspace(
        db_session,
        "lease-dedupe@example.com",
    )
    first = await claim_integration_lease(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        resource_type="shopify_orders",
        owner_token="worker-a",
        ttl_seconds=300,
    )
    await db_session.commit()
    second = await claim_integration_lease(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        resource_type="shopify_orders",
        owner_token="worker-b",
        ttl_seconds=300,
    )
    await db_session.commit()

    assert first is not None
    assert second is None
    assert first.owner_token == "worker-a"

    first.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    third = await claim_integration_lease(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        resource_type="shopify_orders",
        owner_token="worker-b",
        ttl_seconds=300,
    )
    await db_session.commit()

    assert third is not None
    assert third.owner_token == "worker-b"
    await release_integration_lease(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        resource_type="shopify_orders",
        owner_token="worker-b",
    )
    await db_session.commit()
    assert (
        await db_session.execute(
            select(IntegrationLease).where(
                IntegrationLease.workspace_id == workspace.id
            )
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_shopify_order_webhook_records_once(client, db_session, monkeypatch):
    _user, workspace = await _workspace(
        db_session,
        "webhook-route@example.com",
    )
    channel = ShopifyChannel(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        shop_name="webhook-store.myshopify.com",
        shop_domain="webhook-store.myshopify.com",
        access_token="not-used",
        is_active=True,
    )
    db_session.add(channel)
    await db_session.commit()
    body = b'{"id":9001,"fulfillment_status":null}'
    secret = "webhook-secret"
    signature = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    monkeypatch.setattr("app.routers.shopify.settings.SHOPIFY_API_SECRET", secret)
    headers = {
        "X-Shopify-Shop-Domain": "webhook-store.myshopify.com",
        "X-Shopify-Webhook-Id": "event-9001",
        "X-Shopify-Topic": "orders/updated",
        "X-Shopify-Hmac-Sha256": signature,
        "Content-Type": "application/json",
    }

    first = await client.post(
        "/api/v1/shopify/webhooks/orders",
        content=body,
        headers=headers,
    )
    second = await client.post(
        "/api/v1/shopify/webhooks/orders",
        content=body,
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["status"] == "received"
    assert second.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_received_order_webhook_is_normalized_once(db_session):
    _user, workspace = await _workspace(
        db_session,
        "webhook-normalize@example.com",
    )
    created_at = (
        datetime.now(timezone.utc) - timedelta(hours=30)
    ).isoformat()
    event, created = await record_integration_event(
        db_session,
        workspace_id=workspace.id,
        channel_id="shopify-1",
        provider="shopify",
        external_event_id="event-normalize-1",
        event_type="orders/updated",
        external_resource_id="order-77",
        payload={
            "id": 77,
            "name": "#77",
            "created_at": created_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "fulfillment_status": None,
            "financial_status": "paid",
            "cancelled_at": None,
        },
        fingerprint="shopify:event:normalize-1",
        signature_verified=True,
    )
    assert created is True

    result = await process_pending_integration_events(db_session)
    await db_session.commit()
    await db_session.refresh(event)
    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id,
            )
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    second = await process_pending_integration_events(db_session)

    assert result["processed"] == 1
    assert second["processed"] == 0
    assert event.status == "normalized"
    assert signal.source_id == "77"
    assert work.requires_action == "confirm"


@pytest.mark.asyncio
async def test_malformed_webhook_payload_is_marked_failed(db_session):
    _user, workspace = await _workspace(
        db_session,
        "webhook-failed@example.com",
    )
    event = IntegrationEvent(
        workspace_id=workspace.id,
        channel_id="shopify-1",
        provider="shopify",
        external_event_id="event-failed-1",
        event_type="orders/updated",
        payload_json="{not-json",
        fingerprint="shopify:event:failed-1",
        signature_verified=True,
        status="received",
    )
    db_session.add(event)
    await db_session.commit()

    result = await process_pending_integration_events(db_session)
    await db_session.commit()
    await db_session.refresh(event)

    assert result["failed"] == 1
    assert event.status == "retryable_failed"
    assert event.error_code == "payload_invalid"
    assert event.attempts == 1
    assert event.available_at is not None


@pytest.mark.asyncio
async def test_event_moves_to_dead_letter_after_max_attempts(db_session):
    _user, workspace = await _workspace(
        db_session,
        "webhook-dead-letter@example.com",
    )
    event = IntegrationEvent(
        workspace_id=workspace.id,
        channel_id="shopify-1",
        provider="shopify",
        external_event_id="event-dead-1",
        event_type="orders/updated",
        payload_json="{not-json",
        fingerprint="shopify:event:dead-1",
        signature_verified=True,
        status="received",
        attempts=4,
        max_attempts=5,
    )
    db_session.add(event)
    await db_session.commit()

    await process_pending_integration_events(db_session)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.attempts == 5
    assert event.status == "dead_letter"
    assert event.error_code == "payload_invalid"


@pytest.mark.asyncio
async def test_manual_replay_resets_dead_letter_for_processing(db_session):
    _user, workspace = await _workspace(
        db_session,
        "webhook-replay@example.com",
    )
    event = IntegrationEvent(
        workspace_id=workspace.id,
        channel_id="shopify-1",
        provider="shopify",
        external_event_id="event-replay-1",
        event_type="orders/updated",
        payload_json="{not-json",
        fingerprint="shopify:event:replay-1",
        signature_verified=True,
        status="dead_letter",
        attempts=5,
        max_attempts=5,
        error_code="payload_invalid",
    )
    db_session.add(event)
    await db_session.commit()

    replayed = await retry_integration_event(
        db_session,
        workspace_id=workspace.id,
        event_id=event.id,
    )
    await db_session.commit()

    assert replayed.status == "received"
    assert replayed.attempts == 0
    assert replayed.error_code is None
    assert replayed.available_at is not None
