"""Temu LOCAL/SEMI 价格变更提交、审核门禁和回读测试。"""

import json
from uuid import uuid4

import httpx
import pytest

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
from app.services.action_runtime import plan_action_run
from app.services.temu_price_adapter import TemuPriceUpdateActionAdapter
from app.services.temu_price import (
    TemuPriceService,
    build_temu_price_change_payload,
)
from app.services.temu_open_api import TemuOpenApiService
from app.services.workspaces import ensure_personal_workspace


def test_build_temu_price_change_payload_uses_supplier_price():
    payload = build_temu_price_change_payload(
        goods_id=9001,
        sku_id=7001,
        amount="19.99",
        currency="USD",
        reason="卖家确认供货价调整",
    )

    assert payload == {
        "goodsId": 9001,
        "changeSkuPriceDTOList": [
            {
                "reason": "卖家确认供货价调整",
                "skuChangePriceBaseDTOList": [
                    {
                        "skuId": 7001,
                        "newSupplierPrice": {
                            "amount": "19.99",
                            "currency": "USD",
                        },
                    }
                ],
            }
        ],
    }


def test_build_temu_price_change_payload_rejects_invalid_amount():
    with pytest.raises(ValueError, match="大于 0"):
        build_temu_price_change_payload(
            goods_id=9001,
            sku_id=7001,
            amount="0",
            currency="USD",
            reason="调整",
        )
    with pytest.raises(ValueError, match="币种"):
        build_temu_price_change_payload(
            goods_id=9001,
            sku_id=7001,
            amount="1.00",
            currency="",
            reason="调整",
        )


async def _price_context(db_session, email: str):
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
        account_name="Temu Price Store",
        external_account_id=f"mall-price-{user.id}",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"price-token"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "local",
                "api_scope_list": [
                    "bg.local.goods.list.query",
                    "bg.local.goods.priceorder.query",
                    "bg.local.goods.priceorder.change.sku.price",
                ],
            }
        ),
    )
    product = Product(
        user_id=user.id,
        workspace_id=workspace.id,
        url=f"https://detail.1688.com/offer/{uuid4().hex}.html",
        title="Price Product",
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
        title="Price Product",
        version=1,
        content_hash="d" * 64,
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
async def test_temu_price_preflight_execute_and_verify(db_session):
    user, workspace, connection, _product, listing, variant = (
        await _price_context(
            db_session,
            "temu-price-flow@example.com",
        )
    )
    state = {"submitted": False}

    class FakeService:
        async def get_product_sku(self, **kwargs):
            assert kwargs["goods_id"] == 9001
            assert kwargs["out_sku_sn"] == "SKU-BLACK"
            return {
                "goods_id": 9001,
                "sku_id": 7001,
                "out_sku_sn": "SKU-BLACK",
            }

        async def get_price_workflow(self, **kwargs):
            rows = [
                {
                    "order_id": "old-1",
                    "status": 201,
                    "raw": {"orderId": "old-1", "status": 201},
                }
            ]
            if state["submitted"]:
                rows.append(
                    {
                        "order_id": "new-1",
                        "status": 100,
                        "raw": {"orderId": "new-1", "status": 100},
                    }
                )
            return {
                "goods_id": 9001,
                "price_audit_list": rows,
                "allows_change": True,
                "blocked_orders": [],
            }

        async def submit_price_change(self, **kwargs):
            state["submitted"] = True
            return {
                "goods_id": 9001,
                "sku_id": 7001,
                "amount": "22.50",
                "currency": "USD",
                "accepted": True,
            }

    adapter = TemuPriceUpdateActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
    )
    input_data = {
        "listing_id": str(listing.id),
        "connection_id": str(connection.id),
        "variant_id": str(variant.id),
        "amount": "22.50",
        "currency": "USD",
        "reason": "卖家确认供货价调整",
    }
    before = await adapter.preflight(
        action_id="temu.pricing.submit",
        target_id=str(listing.id),
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="temu.pricing.submit",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="temu-price-submit-1",
    )
    verification = await adapter.verify(
        action_id="temu.pricing.submit",
        target_id=str(listing.id),
        execution=execution,
    )

    assert before["current_local_price"] == "19.99"
    assert before["amount"] == "22.50"
    assert before["sku_id"] == 7001
    assert state["submitted"] is True
    assert verification.matched is True
    assert verification.snapshot["state"] == "submitted_for_review"
    assert verification.snapshot["new_order_ids"] == ["new-1"]


@pytest.mark.asyncio
async def test_temu_price_rejects_blocked_workflow_and_bad_scope(db_session):
    user, workspace, connection, _product, listing, variant = (
        await _price_context(
            db_session,
            "temu-price-blocked@example.com",
        )
    )

    class FakeService:
        async def get_product_sku(self, **kwargs):
            return {
                "goods_id": 9001,
                "sku_id": 7001,
                "out_sku_sn": "SKU-BLACK",
            }

        async def get_price_workflow(self, **kwargs):
            return {
                "goods_id": 9001,
                "price_audit_list": [
                    {
                        "order_id": "review-1",
                        "status": 100,
                        "raw": {"status": 100},
                    }
                ],
                "allows_change": False,
                "blocked_orders": [{"order_id": "review-1", "status": 100}],
            }

    adapter = TemuPriceUpdateActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
    )
    input_data = {
        "listing_id": str(listing.id),
        "connection_id": str(connection.id),
        "variant_id": str(variant.id),
        "amount": "22.50",
        "currency": "USD",
        "reason": "卖家确认供货价调整",
    }
    with pytest.raises(ValueError, match="审核"):
        await adapter.preflight(
            action_id="temu.pricing.submit",
            target_id=str(listing.id),
            input_data=input_data,
        )
    with pytest.raises(ValueError, match="大于 0"):
        await adapter.preflight(
            action_id="temu.pricing.submit",
            target_id=str(listing.id),
            input_data={**input_data, "amount": "0"},
        )

    connection.metadata_json = json.dumps(
        {
            "store_type": "crossborder",
            "api_scope_list": [
                "bg.local.goods.list.query",
                "bg.local.goods.priceorder.query",
                "bg.local.goods.priceorder.change.sku.price",
            ],
        }
    )
    await db_session.commit()
    real_adapter = TemuPriceUpdateActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
    )
    with pytest.raises(ValueError, match="LOCAL/SEMI"):
        await real_adapter.preflight(
            action_id="temu.pricing.submit",
            target_id=str(listing.id),
            input_data=input_data,
        )


@pytest.mark.asyncio
async def test_temu_price_service_maps_sku_checks_workflow_and_submits(
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
        await _price_context(
            db_session,
            "temu-price-service@example.com",
        )
    )
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body["type"] == "bg.local.goods.list.query":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "goodsList": [
                            {
                                "goodsId": 9001,
                                "skuInfoList": [
                                    {
                                        "skuId": 7001,
                                        "skuSn": "SKU-BLACK",
                                    }
                                ],
                            }
                        ]
                    },
                },
            )
        if body["type"] == "bg.local.goods.priceorder.query":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "priceAuditList": [
                            {"orderId": "old-1", "status": 201}
                        ]
                    },
                },
            )
        if (
            body["type"]
            == "bg.local.goods.priceorder.change.sku.price"
        ):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {},
                },
            )
        raise AssertionError(body["type"])

    service = TemuPriceService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    remote_sku = await service.get_product_sku(
        connection_id=connection.id,
        goods_id=9001,
        out_sku_sn="SKU-BLACK",
    )
    workflow = await service.get_price_workflow(
        connection_id=connection.id,
        goods_id=9001,
    )
    submitted = await service.submit_price_change(
        connection_id=connection.id,
        goods_id=9001,
        sku_id=7001,
        amount="22.50",
        currency="USD",
        reason="卖家确认供货价调整",
    )

    assert remote_sku["sku_id"] == 7001
    assert workflow["allows_change"] is True
    assert requests[1]["priceOrderType"] == 2
    change_request = requests[2]
    assert change_request["goodsId"] == 9001
    assert change_request["changeSkuPriceDTOList"][0][
        "skuChangePriceBaseDTOList"
    ][0]["newSupplierPrice"] == {
        "amount": "22.50",
        "currency": "USD",
    }
    assert submitted["accepted"] is True
    assert "price-token" not in json.dumps(submitted)


@pytest.mark.asyncio
async def test_temu_price_service_rejects_ambiguous_sku_and_blocked_workflow(
    db_session,
):
    user, _workspace, connection, _product, _listing, _variant = (
        await _price_context(
            db_session,
            "temu-price-ambiguous@example.com",
        )
    )

    class FakeOpenApi:
        mode = "ambiguous"

        async def request(self, **kwargs):
            if kwargs["api_type"] == "bg.local.goods.list.query":
                return {
                    "result": {
                        "goodsList": [
                            {
                                "goodsId": 9001,
                                "skuInfoList": [
                                    {"skuId": 7001, "skuSn": "SKU-BLACK"},
                                    {"skuId": 7002, "skuSn": "SKU-BLACK"},
                                ],
                            }
                        ]
                    }
                }
            return {
                "result": {
                    "priceAuditList": [
                        {"orderId": "review-1", "status": 100},
                        {"orderId": "old-1", "status": 201},
                    ]
                }
            }

    service = TemuPriceService(
        db_session,
        user_id=user.id,
        open_api=FakeOpenApi(),
    )
    with pytest.raises(ValueError, match="不唯一"):
        await service.get_product_sku(
            connection_id=connection.id,
            goods_id=9001,
            out_sku_sn="SKU-BLACK",
        )
    workflow = await service.get_price_workflow(
        connection_id=connection.id,
        goods_id=9001,
    )
    assert workflow["allows_change"] is False
    assert workflow["blocked_orders"][0]["order_id"] == "review-1"


@pytest.mark.asyncio
async def test_temu_price_service_translates_review_error(
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
        await _price_context(
            db_session,
            "temu-price-review-error@example.com",
        )
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "errorCode": 150011103,
                "errorMsg": "Pending price confirmation",
            },
        )

    service = TemuPriceService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    with pytest.raises(ValueError, match="确认"):
        await service.submit_price_change(
            connection_id=connection.id,
            goods_id=9001,
            sku_id=7001,
            amount="22.50",
            currency="USD",
            reason="卖家确认供货价调整",
        )


@pytest.mark.asyncio
async def test_temu_price_plan_preview_and_dispatcher(db_session):
    user, workspace, connection, _product, listing, variant = (
        await _price_context(
            db_session,
            "temu-price-plan@example.com",
        )
    )
    from app.models.agent_work import WorkItem

    work = WorkItem(
        workspace_id=workspace.id,
        kind="pricing_action",
        source="integration",
        title="Temu 价格待调整",
        summary="检查新供货价",
        status="waiting_user",
        requires_action="confirm",
        current_step="等待确认价格",
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=work.id,
        action_id="temu.pricing.submit",
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
            "current_local_price": "19.99",
            "amount": "22.50",
            "currency": "USD",
            "reason": "卖家确认供货价调整",
        },
        idempotency_key="temu-price-plan-1",
    )
    preview = build_action_preview(run, fallback_title="Temu 价格")
    adapter = await resolve_action_adapter(db_session, run)

    assert run.status == "awaiting_confirmation"
    assert preview.title == "即将提交 Temu 价格变更"
    assert any(
        field.label == "新供货价"
        and field.value == "USD 22.50"
        for field in preview.fields
    )
    assert isinstance(adapter, TemuPriceUpdateActionAdapter)


@pytest.mark.asyncio
async def test_agent_prepares_temu_price_without_submit(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    user, workspace, connection, _product, listing, variant = (
        await _price_context(
            db_session,
            "temu-price-agent@example.com",
        )
    )
    submitted = {"value": 0}

    async def fake_preflight(self, *, action_id, target_id, input_data):
        assert action_id == "temu.pricing.submit"
        assert target_id == str(listing.id)
        return {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "connection_id": str(connection.id),
            "goods_id": 9001,
            "sku_id": 7001,
            "current_local_price": "19.99",
            "amount": "22.50",
            "currency": "USD",
            "reason": "卖家确认供货价调整",
            "current_price_order_ids": ["old-1"],
        }

    async def fake_execute(self, **kwargs):
        submitted["value"] += 1

    monkeypatch.setattr(
        TemuPriceUpdateActionAdapter,
        "preflight",
        fake_preflight,
    )
    monkeypatch.setattr(
        TemuPriceUpdateActionAdapter,
        "execute",
        fake_execute,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "submit_temu_price_change",
        {
            "listing_id": str(listing.id),
            "connection_id": str(connection.id),
            "variant_id": str(variant.id),
            "amount": "22.50",
            "currency": "USD",
            "reason": "卖家确认供货价调整",
        },
    )

    assert submitted["value"] == 0
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "temu.pricing.submit"
    assert pending["params"]["amount"] == "22.50"


def test_agent_registers_temu_price_tool():
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "submit_temu_price_change" in names
