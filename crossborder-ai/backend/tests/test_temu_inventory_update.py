"""Temu LOCAL/SEMI 库存覆写请求、动作和回读测试。"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_signal import AgentSignal
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services import provider_config
from app.services.action_dispatcher import resolve_action_adapter
from app.services.action_previews import build_action_preview
from app.services.action_runtime import ActionExecution, plan_action_run
from app.services.temu_inventory_adapter import (
    TemuInventoryUpdateActionAdapter,
)
from app.services.temu_inventory import (
    TemuInventoryService,
    build_temu_stock_payload,
)
from app.services.temu_open_api import TemuOpenApiService
from app.services.workspaces import ensure_personal_workspace


def test_build_temu_stock_payload_uses_target_not_delta():
    payload = build_temu_stock_payload(
        goods_id=9001,
        sku_id=7001,
        stock_target=20,
        request_unique_key="temu-stock-9001-7001-20",
    )

    assert payload == {
        "request": {
            "goodsId": 9001,
            "stockType": 0,
            "skuStockTargetList": [
                {"skuId": 7001, "stockTarget": 20}
            ],
            "requestUniqueKey": "temu-stock-9001-7001-20",
        }
    }
    assert "skuStockChangeList" not in payload["request"]


async def _inventory_context(db_session, email: str):
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
        account_name="Temu Inventory Store",
        external_account_id=f"mall-stock-{user.id}",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"stock-token"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "local",
                "api_scope_list": [
                    "temu.goods.stock.query",
                    "bg.local.goods.stock.edit",
                ],
            }
        ),
    )
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        url=f"https://detail.1688.com/offer/{uuid4().hex}.html",
        title="Inventory Product",
    )
    db_session.add_all([connection, product])
    await db_session.flush()
    variant = ProductVariant(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        sku="SKU-BLACK",
        name="Black",
        price=19.99,
        stock_quantity=8,
        is_active=True,
    )
    listing = ListingDraft(
        user_id=user.id,
        workspace_id=workspace.id,
        product_id=product.id,
        platform="temu",
        language="en",
        tone="professional",
        status="published",
        title="Inventory Product",
        version=1,
        content_hash="c" * 64,
        compliance_status="passed",
    )
    db_session.add_all([variant, listing])
    await db_session.flush()
    signal = AgentSignal(
        workspace_id=workspace.id,
        source_type="temu_listing",
        source_id="9001",
        signal_type="temu_listing_processing",
        severity="normal",
        fingerprint=f"temu-listing:{connection.id}:9001:processing",
        version=2,
        payload_json=json.dumps(
            {
                "connection_id": str(connection.id),
                "listing_id": str(listing.id),
                "goods_id": 9001,
                "external_goods_id": str(product.id),
            }
        ),
        status="resolved",
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(connection)
    await db_session.refresh(product)
    await db_session.refresh(variant)
    await db_session.refresh(listing)
    return user, workspace, connection, product, listing, variant


@pytest.mark.asyncio
async def test_temu_inventory_preflight_execute_and_verify(db_session):
    user, workspace, connection, product, listing, variant = (
        await _inventory_context(
            db_session,
            "temu-inventory-flow@example.com",
        )
    )
    state = {"stock": 8, "updated": None}

    class FakeService:
        async def get_stock(self, *, connection_id, goods_id, out_sku_sns):
            assert connection_id == connection.id
            assert goods_id == 9001
            assert out_sku_sns == ["SKU-BLACK"]
            return {
                "goods_id": 9001,
                "skus": [
                    {
                        "sku_id": 7001,
                        "out_sku_sn": "SKU-BLACK",
                        "stock": state["stock"],
                    }
                ],
            }

        async def update_stock(self, **kwargs):
            state["updated"] = kwargs
            state["stock"] = kwargs["stock_target"]
            return {
                "goods_id": 9001,
                "sku_id": 7001,
                "stock_target": kwargs["stock_target"],
                "succeeded": True,
            }

    adapter = TemuInventoryUpdateActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
    )
    input_data = {
        "listing_id": str(listing.id),
        "connection_id": str(connection.id),
        "variant_id": str(variant.id),
        "stock_target": 20,
    }
    before = await adapter.preflight(
        action_id="temu.inventory.update",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="temu.inventory.update",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="temu-stock-update-1",
    )
    verification = await adapter.verify(
        action_id="temu.inventory.update",
        target_id=str(listing.id),
        execution=execution,
    )

    assert before["current_stock"] == 8
    assert before["stock_target"] == 20
    assert before["goods_id"] == 9001
    assert before["sku_id"] == 7001
    assert state["updated"]["sku_id"] == 7001
    assert state["updated"]["stock_target"] == 20
    assert verification.matched is True
    await db_session.refresh(variant)
    assert variant.stock_quantity == 20


@pytest.mark.asyncio
async def test_temu_inventory_rejects_ambiguous_sku_and_bad_store(db_session):
    user, workspace, connection, _product, listing, variant = (
        await _inventory_context(
            db_session,
            "temu-inventory-security@example.com",
        )
    )

    class FakeService:
        async def get_stock(self, **kwargs):
            return {
                "goods_id": 9001,
                "skus": [
                    {
                        "sku_id": 7001,
                        "out_sku_sn": "SKU-BLACK",
                        "stock": 8,
                    },
                    {
                        "sku_id": 7002,
                        "out_sku_sn": "SKU-BLACK",
                        "stock": 9,
                    },
                ],
            }

    adapter = TemuInventoryUpdateActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
    )
    input_data = {
        "listing_id": str(listing.id),
        "connection_id": str(connection.id),
        "variant_id": str(variant.id),
        "stock_target": 20,
    }
    with pytest.raises(ValueError, match="不唯一"):
        await adapter.preflight(
            action_id="temu.inventory.update",
            target_id=str(listing.id),
            input_data=input_data,
        )
    with pytest.raises(ValueError, match="0 至 1000000"):
        await adapter.preflight(
            action_id="temu.inventory.update",
            target_id=str(listing.id),
            input_data={**input_data, "stock_target": 1_000_001},
        )

    connection.metadata_json = json.dumps(
        {
            "store_type": "crossborder",
            "api_scope_list": [
                "temu.goods.stock.query",
                "bg.local.goods.stock.edit",
            ],
        }
    )
    await db_session.commit()
    real_service = TemuInventoryUpdateActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
    )
    with pytest.raises(ValueError, match="LOCAL/SEMI"):
        await real_service.preflight(
            action_id="temu.inventory.update",
            target_id=str(listing.id),
            input_data=input_data,
        )


@pytest.mark.asyncio
async def test_temu_inventory_service_queries_and_updates_stock(
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
    user, _workspace, connection, _product, _listing, _variant = (
        await _inventory_context(
            db_session,
            "temu-inventory-service@example.com",
        )
    )
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body["type"] == "temu.goods.stock.query":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "stockList": [
                            {
                                "goodsId": 9001,
                                "skuStockInfoList": [
                                    {
                                        "skuId": 7001,
                                        "outSkuSn": "SKU-BLACK",
                                        "selfOrdinaryStock": {"stock": 8},
                                    }
                                ],
                            }
                        ]
                    },
                },
            )
        if body["type"] == "bg.local.goods.stock.edit":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "goodsId": 9001,
                    "operateResult": True,
                    "skuStockEditStatusInfoList": [
                        {
                            "skuId": 7001,
                            "stockEditStatus": True,
                        }
                    ],
                },
            )
        raise AssertionError(body["type"])

    service = TemuInventoryService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    stock = await service.get_stock(
        connection_id=connection.id,
        goods_id=9001,
        out_sku_sns=["SKU-BLACK"],
    )
    updated = await service.update_stock(
        connection_id=connection.id,
        goods_id=9001,
        sku_id=7001,
        stock_target=20,
        request_unique_key="temu-stock-request-1",
    )

    assert stock["skus"][0]["stock"] == 8
    assert requests[0]["type"] == "temu.goods.stock.query"
    assert requests[1]["type"] == "bg.local.goods.stock.edit"
    edit_request = requests[1]["request"]
    assert edit_request["skuStockTargetList"] == [
        {"skuId": 7001, "stockTarget": 20}
    ]
    assert "skuStockChangeList" not in edit_request
    assert updated["succeeded"] is True
    assert "stock-token" not in json.dumps(updated)


@pytest.mark.asyncio
async def test_temu_inventory_service_surfaces_platform_failure(
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
    user, _workspace, connection, _product, _listing, _variant = (
        await _inventory_context(
            db_session,
            "temu-inventory-failure@example.com",
        )
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "errorCode": 1000000,
                "goodsId": 9001,
                "operateResult": False,
                "skuStockEditStatusInfoList": [
                    {
                        "skuId": 7001,
                        "stockEditStatus": False,
                        "errorMsg": "库存同步失败",
                    }
                ],
            },
        )

    service = TemuInventoryService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(ValueError, match="库存同步失败"):
        await service.update_stock(
            connection_id=connection.id,
            goods_id=9001,
            sku_id=7001,
            stock_target=20,
            request_unique_key="temu-stock-failure",
        )


@pytest.mark.asyncio
async def test_temu_inventory_plan_preview_and_dispatcher(db_session):
    user, workspace, connection, _product, listing, variant = (
        await _inventory_context(
            db_session,
            "temu-inventory-plan@example.com",
        )
    )
    from app.models.agent_work import WorkItem

    work = WorkItem(
        workspace_id=workspace.id,
        kind="inventory_action",
        source="integration",
        title="Temu 库存待调整",
        summary="检查目标库存",
        status="waiting_user",
        requires_action="confirm",
        current_step="等待确认库存",
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=work.id,
        action_id="temu.inventory.update",
        platform="temu",
        target_type="listing",
        target_id=str(listing.id),
        input_data={
            "listing_id": str(listing.id),
            "connection_id": str(connection.id),
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "goods_id": 9001,
            "sku_id": 7001,
            "current_stock": 8,
            "stock_target": 20,
        },
        idempotency_key="temu-inventory-plan-1",
    )
    preview = build_action_preview(run, fallback_title="Temu 库存")
    adapter = await resolve_action_adapter(db_session, run)

    assert run.status == "awaiting_confirmation"
    assert preview.title == "即将更新 Temu 库存"
    assert any(
        field.label == "库存"
        and field.value == "8 → 20 件"
        for field in preview.fields
    )
    assert isinstance(adapter, TemuInventoryUpdateActionAdapter)


@pytest.mark.asyncio
async def test_agent_prepares_temu_inventory_without_submit(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, connection, _product, listing, variant = (
        await _inventory_context(
            db_session,
            "temu-inventory-agent@example.com",
        )
    )
    submitted = {"value": 0}

    async def fake_preflight(self, *, action_id, target_id, input_data):
        assert action_id == "temu.inventory.update"
        assert target_id == str(listing.id)
        return {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "connection_id": str(connection.id),
            "goods_id": 9001,
            "sku_id": 7001,
            "current_stock": 8,
            "stock_target": 20,
        }

    async def fake_execute(self, **kwargs):
        submitted["value"] += 1

    monkeypatch.setattr(
        TemuInventoryUpdateActionAdapter,
        "preflight",
        fake_preflight,
    )
    monkeypatch.setattr(
        TemuInventoryUpdateActionAdapter,
        "execute",
        fake_execute,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "update_temu_inventory",
        {
            "listing_id": str(listing.id),
            "connection_id": str(connection.id),
            "variant_id": str(variant.id),
            "stock_target": 20,
        },
    )

    assert submitted["value"] == 0
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "temu.inventory.update"
    assert pending["params"]["stock_target"] == 20


def test_agent_registers_temu_inventory_tool():
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "update_temu_inventory" in names
