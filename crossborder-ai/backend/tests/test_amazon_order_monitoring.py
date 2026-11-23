"""Amazon FBM 订单读取、区域选择与 Agent 信号同步测试。"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import decrypt_value, encrypt_value
from app.models.agent_signal import AgentSignal, IntegrationCursor
from app.models.agent_work import WorkItem
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services.amazon_orders import (
    AmazonOrdersService,
    AmazonRateLimitError,
    resolve_amazon_region,
    sync_amazon_order_signals,
)
from app.services.workspaces import ensure_personal_workspace


def _configure_amazon(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import provider_config

    monkeypatch.setattr(
        provider_config.settings,
        "AMAZON_APP_ID",
        "amzn1.sp.solution.test",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "AMAZON_CLIENT_ID",
        "amzn1.application-oa2-client.test",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "AMAZON_CLIENT_SECRET",
        "amazon-client-secret",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "AMAZON_REDIRECT_URI",
        "https://example.com/api/v1/platforms/amazon/callback",
        raising=False,
    )
    provider_config.clear_cache()


def _order(
    order_id: str,
    *,
    status: str = "UNSHIPPED",
    fulfilled_by: str = "MERCHANT",
    age_hours: int = 30,
    marketplace_id: str = "ATVPDKIKX0DER",
):
    now = datetime.now(timezone.utc)
    return {
        "orderId": order_id,
        "createdTime": (now - timedelta(hours=age_hours)).isoformat(),
        "lastUpdatedTime": now.isoformat(),
        "salesChannel": {"marketplaceId": marketplace_id},
        "fulfillment": {
            "fulfilledBy": fulfilled_by,
            "fulfillmentStatus": status,
        },
        "orderItems": [
            {
                "orderItemId": "item-1",
                "quantityOrdered": 2,
                "product": {
                    "sellerSku": "SKU-1",
                    "title": "Test product",
                },
            }
        ],
        "buyer": {
            "email": "private@example.com",
            "name": "Private Buyer",
        },
        "recipient": {"address": "private street"},
    }


async def _context(
    db_session,
    email: str,
    *,
    marketplace_id: str = "ATVPDKIKX0DER",
    country_code: str = "US",
):
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
        platform="amazon",
        account_name="Amazon Test",
        external_account_id="A1SELLER",
        marketplace_id=marketplace_id,
        credentials=encrypt_value(
            json.dumps({"refresh_token": "Atzr|refresh-token"})
        ),
        status="active",
        metadata_json=json.dumps(
            {
                "marketplaces": [
                    {
                        "marketplace": {
                            "id": marketplace_id,
                            "countryCode": country_code,
                        },
                        "participation": {"isParticipating": True},
                    }
                ]
            }
        ),
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)
    return user, workspace, connection


def test_amazon_region_resolution_for_core_marketplaces():
    assert resolve_amazon_region("ATVPDKIKX0DER") == "na"
    assert resolve_amazon_region("A2EUQ1WTGCTBG2") == "na"
    assert resolve_amazon_region("A1PA6795UKMFR9") == "eu"
    assert resolve_amazon_region("A1F83G8C2ARO7P") == "eu"
    assert resolve_amazon_region("A1VC38T7YXB528") == "fe"
    assert resolve_amazon_region("A39IBJ37TRP1C6") == "fe"


@pytest.mark.asyncio
async def test_orders_request_uses_region_and_no_pii():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={"orders": []},
        )

    service = AmazonOrdersService(transport=httpx.MockTransport(handler))
    await service.search_orders(
        access_token="Atza|access",
        marketplace_id="A1PA6795UKMFR9",
        last_updated_after="2026-11-19T00:00:00+00:00",
        fulfillment_statuses=["UNSHIPPED"],
    )

    assert captured["url"].startswith(
        "https://sellingpartnerapi-eu.amazon.com/orders/2026-01-01/orders?"
    )
    assert captured["path"] == "/orders/2026-01-01/orders"
    assert captured["headers"]["x-amz-access-token"] == "Atza|access"
    query = captured["url"].lower()
    assert "fulfilledby=merchant" in query
    assert "includeddata=fulfillment" in query
    assert "fulfillmentstatuses=unshipped" in query
    assert "buyer" not in query
    assert "recipient" not in query
    assert "tax" not in query
    assert "payment" not in query


@pytest.mark.asyncio
async def test_order_sync_creates_sanitized_signal_and_is_idempotent(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    _user, workspace, connection = await _context(
        db_session,
        "amazon-order-sync@example.com",
    )

    async def fake_refresh(self, refresh_token):
        assert refresh_token == "Atzr|refresh-token"
        return "Atza|access"

    async def fake_search(self, **kwargs):
        assert kwargs["marketplace_id"] == "ATVPDKIKX0DER"
        return {
            "orders": [_order("111-2222222-3333333", age_hours=30)],
            "paginationToken": None,
        }

    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(AmazonOrdersService, "search_orders", fake_search)

    first = await sync_amazon_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()
    second = await sync_amazon_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id,
                AgentSignal.signal_type == "amazon_order_awaiting_shipment",
            )
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    cursor = (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id,
                IntegrationCursor.resource_type == "amazon_orders",
            )
        )
    ).scalar_one()
    payload = json.loads(signal.payload_json)
    assert first["signals_created"] == 1
    assert second["signals_updated"] == 1
    assert work.kind == "order_exception"
    assert work.requires_action == "none"
    assert payload["order_id"] == "111-2222222-3333333"
    assert payload["marketplace_id"] == "ATVPDKIKX0DER"
    assert "email" not in json.dumps(payload).lower()
    assert "private" not in json.dumps(payload).lower()
    assert cursor.cursor_value


@pytest.mark.asyncio
async def test_shipped_order_resolves_existing_signal(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    _user, workspace, connection = await _context(
        db_session,
        "amazon-order-resolve@example.com",
    )
    state = {"status": "UNSHIPPED"}

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def fake_search(self, **kwargs):
        return {
            "orders": [
                _order(
                    "111-2222222-4444444",
                    status=state["status"],
                )
            ],
            "paginationToken": None,
        }

    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(AmazonOrdersService, "search_orders", fake_search)

    await sync_amazon_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()
    state["status"] = "SHIPPED"
    result = await sync_amazon_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    signal = (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one()
    work = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert result["signals_resolved"] == 1
    assert signal.status == "resolved"
    assert work.status == "succeeded"


@pytest.mark.asyncio
async def test_fba_order_does_not_create_seller_shipment_task(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    _user, workspace, connection = await _context(
        db_session,
        "amazon-fba-order@example.com",
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def fake_search(self, **kwargs):
        return {
            "orders": [
                _order(
                    "111-2222222-5555555",
                    fulfilled_by="AMAZON",
                )
            ],
            "paginationToken": None,
        }

    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(AmazonOrdersService, "search_orders", fake_search)
    result = await sync_amazon_order_signals(
        db_session,
        workspace_id=workspace.id,
        connection=connection,
    )
    await db_session.commit()

    assert result["signals_created"] == 0
    assert (
        await db_session.execute(
            select(AgentSignal).where(AgentSignal.workspace_id == workspace.id)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_rate_limit_does_not_advance_cursor(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    _user, workspace, connection = await _context(
        db_session,
        "amazon-order-rate@example.com",
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def fake_search(self, **kwargs):
        raise AmazonRateLimitError("Amazon 限流，请稍后重试")

    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(AmazonOrdersService, "search_orders", fake_search)

    with pytest.raises(AmazonRateLimitError):
        await sync_amazon_order_signals(
            db_session,
            workspace_id=workspace.id,
            connection=connection,
        )
    assert (
        await db_session.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace.id
            )
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_authorization_failure_marks_connection_invalid_and_creates_task(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    _user, workspace, connection = await _context(
        db_session,
        "amazon-order-auth@example.com",
    )

    async def fake_refresh(self, refresh_token):
        raise ValueError("Amazon 授权已失效，请重新绑定")

    monkeypatch.setattr(
        "app.services.amazon_orders.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )

    with pytest.raises(ValueError, match="授权已失效"):
        await sync_amazon_order_signals(
            db_session,
            workspace_id=workspace.id,
            connection=connection,
        )
    await db_session.commit()

    await db_session.refresh(connection)
    assert connection.status == "invalid"
    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id,
                AgentSignal.signal_type == "authorization_expired",
            )
        )
    ).scalar_one()
    assert signal.severity == "urgent"
    credentials = json.loads(decrypt_value(connection.credentials))
    assert credentials["refresh_token"] == "Atzr|refresh-token"


@pytest.mark.asyncio
async def test_agent_queries_amazon_orders_without_returning_pii(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    _configure_amazon(monkeypatch)
    user, workspace, _connection = await _context(
        db_session,
        "amazon-order-agent@example.com",
    )

    async def fake_refresh(self, refresh_token):
        return "Atza|access"

    async def fake_search(self, **kwargs):
        assert kwargs["fulfillment_statuses"] == ["UNSHIPPED"]
        return {
            "orders": [
                _order(
                    "111-2222222-6666666",
                    status="UNSHIPPED",
                )
            ]
        }

    monkeypatch.setattr(
        "app.services.ai.agent_orchestrator.AmazonSpApiService.refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(AmazonOrdersService, "search_orders", fake_search)
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "search_amazon_orders",
        {
            "marketplace_id": "ATVPDKIKX0DER",
            "days": 7,
            "fulfillment_statuses": ["UNSHIPPED"],
        },
    )

    assert result["status"] == "success"
    order = result["data"]["orders"][0]
    assert order["order_id"] == "111-2222222-6666666"
    assert order["fulfillment_status"] == "UNSHIPPED"
    assert order["item_count"] == 2
    assert order["skus"] == ["SKU-1"]
    response_text = json.dumps(result, ensure_ascii=False).lower()
    assert "private@example.com" not in response_text
    assert "private buyer" not in response_text
    assert "private street" not in response_text


def test_agent_registers_amazon_order_read_tool():
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "search_amazon_orders" in names
