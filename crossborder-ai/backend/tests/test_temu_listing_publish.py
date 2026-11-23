"""Temu 商品发布 V3 请求、图片和动作闭环测试。"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_signal import AgentSignal
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services import provider_config
from app.services.action_dispatcher import resolve_action_adapter
from app.services.action_previews import build_action_preview
from app.services.action_runtime import ActionExecution, plan_action_run
from app.services.temu_listing_publish_adapter import (
    TemuListingPublishActionAdapter,
)
from app.services.temu_listing_publish import (
    TemuListingPublishService,
    build_temu_listing_payload,
)
from app.services.temu_open_api import TemuOpenApiService
from app.services.workspaces import ensure_personal_workspace


def _product_and_listing():
    product = Product(
        id=uuid4(),
        user_id=uuid4(),
        workspace_id=uuid4(),
        url=f"https://detail.1688.com/offer/{uuid4().hex}.html",
        title="Temu Product",
        description="A factual product description.",
        brand_name="Veya",
        lead_time_days=3,
    )
    listing = ListingDraft(
        id=uuid4(),
        user_id=product.user_id,
        workspace_id=product.workspace_id,
        product_id=product.id,
        platform="temu",
        language="en",
        tone="professional",
        status="ready",
        title="Premium Travel Organizer",
        description="Keep travel essentials organized.",
        bullet_points=json.dumps(["Durable", "Lightweight"]),
        version=1,
        content_hash="a" * 64,
        compliance_status="passed",
    )
    variants = [
        ProductVariant(
            id=uuid4(),
            user_id=product.user_id,
            workspace_id=product.workspace_id,
            product_id=product.id,
            sku="SKU-BLACK",
            name="Black",
            attributes_json=json.dumps(
                {"Color": "Black", "Size": "M"}
            ),
            price=19.99,
            stock_quantity=20,
            barcode="0123456789012",
            is_active=True,
        )
    ]
    return product, listing, variants


async def _publish_context(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    product, listing, variants = _product_and_listing()
    product.user_id = user.id
    product.workspace_id = workspace.id
    listing.user_id = user.id
    listing.workspace_id = workspace.id
    for variant in variants:
        variant.user_id = user.id
        variant.workspace_id = workspace.id
    connection = PlatformConnection(
        user_id=user.id,
        platform="temu",
        account_name="Temu Publish Store",
        external_account_id=f"mall-publish-{user.id}",
        marketplace_id="us",
        credentials=encrypt_value('{"access_token":"temu-token"}'),
        status="active",
        metadata_json=json.dumps(
            {
                "store_type": "local",
                "api_scope_list": [
                    "temu.local.goods.v3.add",
                    "bg.local.goods.list.query",
                    "bg.local.goods.publish.status.get",
                ],
            }
        ),
    )
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=workspace.id,
        name="Main",
        kind="upload",
        category="product",
        storage_key=f"{user.id}/{uuid4()}.jpg",
        content_type="image/jpeg",
        width=1000,
        height=1000,
        file_size=100,
    )
    db_session.add_all([product, listing, *variants, connection, asset])
    await db_session.commit()
    await db_session.refresh(connection)
    await db_session.refresh(asset)
    return user, workspace, connection, product, listing, variants[0], asset


def test_build_temu_listing_payload_uses_real_sku_and_public_images():
    product, listing, variants = _product_and_listing()
    payload = build_temu_listing_payload(
        product,
        listing,
        variants,
        image_urls=["https://cdn.example.com/product.jpg"],
        category_name="Travel / Luggage Accessories",
        currency="USD",
        language="en",
        attributes=[{"name": "Brand", "value": ["Veya"]}],
        package_info={
            "weight": "100",
            "length": "10",
            "width": "20",
            "height": "30",
        },
    )

    assert payload["goodsBasic"]["externalGoodsId"] == str(product.id)
    assert payload["goodsBasic"]["goodsName"] == listing.title
    assert payload["goodsBasic"]["extCatName"] == (
        "Travel / Luggage Accessories"
    )
    assert payload["goodsBasic"]["goodsCarouselImage"] == [
        "https://cdn.example.com/product.jpg"
    ]
    sku = payload["skuList"][0]
    assert sku["externalSkuId"] == "SKU-BLACK"
    assert sku["price"]["basePrice"] == {
        "amount": "19.99",
        "currency": "USD",
    }
    assert sku["quantity"] == 20
    assert sku["packageInfo"]["weight"] == "100"
    assert sku["variations"] == [
        {"name": "Color", "value": "Black"},
        {"name": "Size", "value": "M"},
    ]


def test_build_temu_listing_payload_rejects_unsafe_images_and_partial_package():
    product, listing, variants = _product_and_listing()

    with pytest.raises(ValueError, match="HTTPS"):
        build_temu_listing_payload(
            product,
            listing,
            variants,
            image_urls=["http://localhost/product.jpg"],
            category_name="Travel",
            currency="USD",
            language="en",
        )

    with pytest.raises(ValueError, match="同时提供"):
        build_temu_listing_payload(
            product,
            listing,
            variants,
            image_urls=["https://cdn.example.com/product.jpg"],
            category_name="Travel",
            currency="USD",
            language="en",
            package_info={"weight": "100", "length": ""},
        )


def test_build_temu_listing_payload_does_not_invent_package_info():
    product, listing, variants = _product_and_listing()
    payload = build_temu_listing_payload(
        product,
        listing,
        variants,
        image_urls=["https://cdn.example.com/product.jpg"],
        category_name="Travel",
        currency="USD",
        language="en",
    )

    assert "packageInfo" not in payload["skuList"][0]


@pytest.mark.asyncio
async def test_temu_listing_preflight_validates_assets_without_submit(
    db_session,
):
    (
        user,
        workspace,
        connection,
        _product,
        listing,
        _variant,
        asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-preflight@example.com",
    )

    class FakeService:
        async def submit(self, **kwargs):
            raise AssertionError("预检不能提交 Temu 商品")

    class FakeStorage:
        async def put_bytes(self, *args, **kwargs):
            raise AssertionError("预检不能公开图片")

    adapter = TemuListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
        public_storage=FakeStorage(),
    )
    snapshot = await adapter.preflight(
        action_id="temu.listings.submit",
        target_id=str(listing.id),
        input_data={
            "listing_id": str(listing.id),
            "connection_id": str(connection.id),
            "asset_ids": [str(asset.id)],
            "category_name": "Travel / Luggage Accessories",
            "currency": "USD",
        },
    )

    assert snapshot["listing_id"] == str(listing.id)
    assert snapshot["asset_count"] == 1
    assert snapshot["sku_count"] == 1
    assert snapshot["item_count"] == 20


@pytest.mark.asyncio
async def test_temu_listing_execute_publishes_images_and_verifies_readback(
    db_session,
):
    (
        user,
        workspace,
        connection,
        product,
        listing,
        variant,
        asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-execute@example.com",
    )
    calls = {"payload": None, "read": 0}

    class FakeService:
        async def publish_asset(self, selected_asset, *, storage):
            assert selected_asset.id == asset.id
            return "https://cdn.example.com/product.jpg"

        async def submit(self, *, connection_id, payload):
            assert connection_id == connection.id
            calls["payload"] = payload
            return {
                "goods_id": 9001,
                "external_goods_id": str(product.id),
            }

        async def read_product(self, *, connection_id, goods_id):
            calls["read"] += 1
            assert connection_id == connection.id
            assert goods_id == 9001
            return {
                "goods_id": 9001,
                "external_goods_id": str(product.id),
                "status": 2,
                "sub_status": 5,
            }

    adapter = TemuListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
        public_storage=object(),
    )
    input_data = {
        "listing_id": str(listing.id),
        "connection_id": str(connection.id),
        "asset_ids": [str(asset.id)],
        "category_name": "Travel / Luggage Accessories",
        "currency": "USD",
    }
    execution = await adapter.execute(
        action_id="temu.listings.submit",
        target_id=str(listing.id),
        input_data=input_data,
        idempotency_key="temu-publish-1",
    )
    verification = await adapter.verify(
        action_id="temu.listings.submit",
        target_id=str(listing.id),
        execution=execution,
    )

    assert calls["payload"]["skuList"][0]["externalSkuId"] == variant.sku
    assert calls["payload"]["goodsBasic"]["goodsCarouselImage"] == [
        "https://cdn.example.com/product.jpg"
    ]
    assert execution.external_id == "9001"
    assert execution.output["goods_id"] == 9001
    assert calls["read"] == 1
    assert verification.matched is True
    assert verification.snapshot["raw_status"] == 2
    assert verification.snapshot["state"] == "submitted_processing"
    signal = (
        await db_session.execute(
            select(AgentSignal).where(
                AgentSignal.workspace_id == workspace.id,
                AgentSignal.signal_type == "temu_listing_processing",
            )
        )
    ).scalar_one()
    assert json.loads(signal.payload_json)["goods_id"] == 9001


@pytest.mark.asyncio
async def test_temu_listing_service_submits_v3_and_reads_goods(
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
    (
        user,
        _workspace,
        connection,
        product,
        _listing,
        _variant,
        _asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-service@example.com",
    )
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["type"] == "temu.local.goods.v3.add":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "errorCode": 1000000,
                    "result": {
                        "goodsId": 9001,
                        "externalGoodsId": str(product.id),
                    },
                },
            )
        if body["type"] == "bg.local.goods.list.query":
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
                                "outGoodsSn": str(product.id),
                                "status4VO": 2,
                                "subStatus4VO": 5,
                            }
                        ],
                    },
                },
            )
        raise AssertionError(body["type"])

    service = TemuListingPublishService(
        db_session,
        user_id=user.id,
        open_api=TemuOpenApiService(
            transport=httpx.MockTransport(handler)
        ),
    )
    submitted = await service.submit(
        connection_id=connection.id,
        payload={"goodsBasic": {"goodsName": "Test"}, "skuList": []},
    )
    remote = await service.read_product(
        connection_id=connection.id,
        goods_id=submitted["goods_id"],
    )

    assert submitted == {
        "goods_id": 9001,
        "external_goods_id": str(product.id),
    }
    assert requests[0]["type"] == "temu.local.goods.v3.add"
    assert requests[1]["goodsIdList"] == [9001]
    assert remote["status"] == 2
    assert "temu-token" not in json.dumps(remote, ensure_ascii=False)


@pytest.mark.asyncio
async def test_temu_listing_plan_preview_and_dispatcher(db_session):
    (
        user,
        workspace,
        connection,
        _product,
        listing,
        _variant,
        asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-plan@example.com",
    )
    from app.models.agent_work import WorkItem

    work = WorkItem(
        workspace_id=workspace.id,
        kind="listing_action",
        source="integration",
        title="Temu 商品待发布",
        summary="准备提交 V3 商品",
        status="waiting_user",
        requires_action="confirm",
        current_step="等待确认发布",
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=work.id,
        action_id="temu.listings.submit",
        platform="temu",
        target_type="listing",
        target_id=str(listing.id),
        input_data={
            "listing_id": str(listing.id),
            "connection_id": str(connection.id),
            "asset_ids": [str(asset.id)],
            "asset_count": 1,
            "category_name": "Travel / Luggage Accessories",
            "currency": "USD",
            "sku_count": 1,
            "item_count": 20,
        },
        idempotency_key="temu-listing-plan-1",
    )
    preview = build_action_preview(run, fallback_title="Temu 商品发布")
    adapter = await resolve_action_adapter(db_session, run)

    assert run.status == "awaiting_confirmation"
    assert preview.title == "即将提交 Temu 商品"
    assert preview.platform == "temu"
    assert any(
        field.label == "类目"
        and field.value == "Travel / Luggage Accessories"
        for field in preview.fields
    )
    assert isinstance(adapter, TemuListingPublishActionAdapter)


@pytest.mark.asyncio
async def test_agent_prepares_temu_listing_without_submit(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    (
        user,
        workspace,
        connection,
        _product,
        listing,
        _variant,
        asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-agent@example.com",
    )
    submitted = {"value": 0}

    async def fake_preflight(self, *, action_id, target_id, input_data):
        assert action_id == "temu.listings.submit"
        assert target_id == str(listing.id)
        return {
            "listing_id": str(listing.id),
            "listing_version": 1,
            "product_id": str(listing.product_id),
            "connection_id": str(connection.id),
            "asset_ids": [str(asset.id)],
            "asset_count": 1,
            "sku_count": 1,
            "item_count": 20,
            "category_name": "Travel / Luggage Accessories",
            "currency": "USD",
        }

    async def fake_execute(self, **kwargs):
        submitted["value"] += 1

    monkeypatch.setattr(
        TemuListingPublishActionAdapter,
        "preflight",
        fake_preflight,
    )
    monkeypatch.setattr(
        TemuListingPublishActionAdapter,
        "execute",
        fake_execute,
    )
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )
    result = await orchestrator._execute_step(
        "submit_temu_listing",
        {
            "listing_id": str(listing.id),
            "connection_id": str(connection.id),
            "asset_ids": [str(asset.id)],
            "category_name": "Travel / Luggage Accessories",
            "currency": "USD",
        },
    )

    assert submitted["value"] == 0
    assert result["status"] == "success"
    pending = result["data"]["pending_action"]
    assert pending["action"] == "temu.listings.submit"
    assert pending["params"]["category_name"] == (
        "Travel / Luggage Accessories"
    )


def test_agent_registers_temu_listing_submit_tool():
    from app.services.ai.agent_orchestrator import AgentOrchestrator

    names = {
        tool["function"]["name"]
        for tool in AgentOrchestrator.TOOLS
    }
    assert "submit_temu_listing" in names


@pytest.mark.asyncio
async def test_temu_listing_preflight_rejects_scope_assets_and_category(
    db_session,
):
    (
        user,
        workspace,
        connection,
        _product,
        listing,
        _variant,
        asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-security@example.com",
    )

    class FakeStorage:
        pass

    adapter = TemuListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=object(),
        public_storage=FakeStorage(),
    )
    base_input = {
        "listing_id": str(listing.id),
        "connection_id": str(connection.id),
        "asset_ids": [str(asset.id)],
        "category_name": "",
        "currency": "USD",
    }
    with pytest.raises(ValueError, match="类目"):
        await adapter.preflight(
            action_id="temu.listings.submit",
            target_id=str(listing.id),
            input_data=base_input,
        )

    connection.metadata_json = json.dumps(
        {
            "store_type": "crossborder",
            "api_scope_list": [
                "temu.local.goods.v3.add",
                "bg.local.goods.list.query",
            ],
        }
    )
    await db_session.commit()
    with pytest.raises(ValueError, match="LOCAL/SEMI"):
        await adapter.preflight(
            action_id="temu.listings.submit",
            target_id=str(listing.id),
            input_data={
                **base_input,
                "category_name": "Travel",
            },
        )

    connection.metadata_json = json.dumps(
        {
            "store_type": "local",
            "api_scope_list": ["bg.local.goods.list.query"],
        }
    )
    await db_session.commit()
    with pytest.raises(ValueError, match="scope"):
        await adapter.preflight(
            action_id="temu.listings.submit",
            target_id=str(listing.id),
            input_data={
                **base_input,
                "category_name": "Travel",
            },
        )


def test_builder_rejects_missing_images_variants_and_price():
    product, listing, variants = _product_and_listing()
    with pytest.raises(ValueError, match="公网图片"):
        build_temu_listing_payload(
            product,
            listing,
            variants,
            image_urls=[],
            category_name="Travel",
            currency="USD",
            language="en",
        )

    variants[0].is_active = False
    with pytest.raises(ValueError, match="SKU"):
        build_temu_listing_payload(
            product,
            listing,
            variants,
            image_urls=["https://cdn.example.com/product.jpg"],
            category_name="Travel",
            currency="USD",
            language="en",
        )

    variants[0].is_active = True
    variants[0].price = None
    with pytest.raises(ValueError, match="销售价"):
        build_temu_listing_payload(
            product,
            listing,
            variants,
            image_urls=["https://cdn.example.com/product.jpg"],
            category_name="Travel",
            currency="USD",
            language="en",
        )


@pytest.mark.asyncio
async def test_temu_listing_service_rejects_scope_and_empty_readback(
    db_session,
):
    (
        user,
        _workspace,
        connection,
        _product,
        _listing,
        _variant,
        _asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-empty@example.com",
    )
    connection.metadata_json = json.dumps(
        {"store_type": "local", "api_scope_list": []}
    )
    await db_session.commit()
    service = TemuListingPublishService(
        db_session,
        user_id=user.id,
        open_api=object(),
    )
    with pytest.raises(ValueError, match="scope"):
        await service.submit(
            connection_id=connection.id,
            payload={"goodsBasic": {}, "skuList": []},
        )


@pytest.mark.asyncio
async def test_temu_listing_adapter_verify_rejects_external_id_mismatch(
    db_session,
):
    (
        user,
        workspace,
        connection,
        _product,
        listing,
        _variant,
        _asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-mismatch@example.com",
    )

    class FakeService:
        async def read_product(self, **kwargs):
            return {
                "goods_id": 9001,
                "external_goods_id": "different-product",
                "status": 2,
                "sub_status": 5,
            }

    adapter = TemuListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=FakeService(),
        public_storage=object(),
    )
    verification = await adapter.verify(
        action_id="temu.listings.submit",
        target_id=str(listing.id),
        execution=ActionExecution(
            external_id="9001",
            output={
                "connection_id": str(connection.id),
                "goods_id": 9001,
                "external_goods_id": "expected-product",
            },
        ),
    )

    assert verification.matched is False
    assert "不一致" in verification.details["error"]


@pytest.mark.asyncio
async def test_temu_listing_preflight_rejects_missing_listing_and_asset(
    db_session,
):
    (
        user,
        workspace,
        connection,
        _product,
        listing,
        _variant,
        _asset,
    ) = await _publish_context(
        db_session,
        "temu-publish-missing@example.com",
    )

    class FakeStorage:
        pass

    adapter = TemuListingPublishActionAdapter(
        db_session,
        user_id=user.id,
        workspace_id=workspace.id,
        service=object(),
        public_storage=FakeStorage(),
    )
    with pytest.raises(ValueError, match="Listing"):
        await adapter.preflight(
            action_id="temu.listings.submit",
            target_id=str(uuid4()),
            input_data={
                "connection_id": str(connection.id),
                "asset_ids": [str(uuid4())],
                "category_name": "Travel",
                "currency": "USD",
            },
        )
    with pytest.raises(ValueError, match="素材"):
        await adapter.preflight(
            action_id="temu.listings.submit",
            target_id=str(listing.id),
            input_data={
                "listing_id": str(listing.id),
                "connection_id": str(connection.id),
                "asset_ids": [str(uuid4())],
                "category_name": "Travel",
                "currency": "USD",
            },
        )
