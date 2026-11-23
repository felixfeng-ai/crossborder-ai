"""Temu 开放平台签名、授权连接与凭据保护测试。"""

import json
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import text

from app.core.crypto import decrypt_value
from app.services import provider_config
from app.services import temu_open_api


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _configure_temu(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_REDIRECT_URI",
        "https://example.com/api/v1/platforms/temu/callback",
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_DEFAULT_REGION",
        "global",
        raising=False,
    )
    provider_config.clear_cache()


def test_temu_signature_matches_official_example():
    """签名算法必须与 Temu 官方示例一致，不能只做格式正确。"""

    params = {
        "access_token": "2nifvmpyymvypwmcms5ct4uqqudrwgpmzbcnmkt1jzjkuaf3x56iixym",
        "app_key": "f9d5cc9313893a20d5aa85c654e8f503",
        "data_type": "JSON",
        "sendRequestList": [
            {
                "orderSendInfoList": [
                    {
                        "quantity": 1,
                        "orderSn": "211-21905473070712792",
                        "parentOrderSn": "PO-211-21905452099192792",
                        "goodsId": 601099548666279,
                        "skuId": 17592352673534,
                    }
                ],
                "carrierId": "699272611",
                "trackingNumber": "270324232756",
            }
        ],
        "sendType": 0,
        "timestamp": 1711009072,
        "type": "bg.logistics.shipment.confirm",
    }

    assert (
        temu_open_api.TemuOpenApiService.generate_sign(
            params,
            "c7e0a1a63542be4de3cb5488f9fba8149e8fc290",
        )
        == "4CCF219942D4180C6DDA3CE36C1B838F"
    )


def test_temu_gateway_region_selection():
    assert temu_open_api.resolve_gateway_region("openapi-b-us.temu.com") == "us"
    assert temu_open_api.resolve_gateway_region("openapi-b-eu.temu.com") == "eu"
    assert (
        temu_open_api.resolve_gateway_region("openapi-b-global.temu.com")
        == "global"
    )
    assert (
        temu_open_api.gateway_url("eu")
        == "https://openapi-b-eu.temu.com/openapi/router"
    )


@pytest.mark.asyncio
async def test_temu_request_uses_signed_json_post_without_secret_in_url(
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    captured: dict = {}

    async def handler(request):
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return Response(
            200,
            json={
                "success": True,
                "errorCode": 1000000,
                "result": {"mallId": 1, "apiScopeList": []},
            },
        )

    service = temu_open_api.TemuOpenApiService(
        transport=MockTransport(handler),
    )
    result = await service.get_token_info("temu-access-token", "eu")

    assert result["mallId"] == 1
    assert captured["method"] == "POST"
    assert captured["url"] == "https://openapi-b-eu.temu.com/openapi/router"
    assert "temu-app-secret" not in captured["url"]
    assert captured["body"]["app_key"] == "temu-app-key"
    assert captured["body"]["access_token"] == "temu-access-token"
    assert captured["body"]["sign"]
    assert "app_secret" not in captured["body"]


@pytest.mark.asyncio
async def test_temu_connect_url_contains_state_without_secret(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    headers = await _register(
        client,
        f"temu-url-{uuid.uuid4().hex[:8]}@test.com",
    )

    response = await client.post(
        "/api/v1/platforms/temu/connect-url",
        headers=headers,
        json={"region": "eu"},
    )
    assert response.status_code == 200, response.text
    auth_url = response.json()["auth_url"]
    parsed = urlparse(auth_url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "seller-eu.temu.com"
    assert query["appKey"] == ["temu-app-key"]
    assert query["redirect_uri"] == [
        "https://example.com/api/v1/platforms/temu/callback"
    ]
    assert query["state"][0]
    assert "temu-app-secret" not in auth_url


@pytest.mark.asyncio
async def test_temu_callback_exchanges_code_and_stores_encrypted_connection(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    headers = await _register(
        client,
        f"temu-callback-{uuid.uuid4().hex[:8]}@test.com",
    )
    connect = await client.post(
        "/api/v1/platforms/temu/connect-url",
        headers=headers,
        json={"region": "us"},
    )
    state = parse_qs(urlparse(connect.json()["auth_url"]).query)["state"][0]

    async def fake_exchange(self, code, region):
        assert code == "temu-auth-code"
        assert region == "us"
        return {
            "accessToken": "temu-access-token-secret",
            "mallId": 1024,
            "expiredTime": 1765634102,
            "apiScopeList": ["bg.order.list.v2.get"],
        }

    monkeypatch.setattr(
        temu_open_api.TemuOpenApiService,
        "exchange_authorization_code",
        fake_exchange,
    )

    callback = await client.get(
        "/api/v1/platforms/temu/callback",
        params={
            "app_key": "temu-app-key",
            "callback_host": "openapi-b-us.temu.com",
            "code": "temu-auth-code",
            "state": state,
        },
        follow_redirects=False,
    )
    assert callback.status_code == 302, callback.text
    assert "temu_connected=1" in callback.headers["location"]

    row = (
        await db_session.execute(
            text(
                "select platform, account_name, external_account_id, "
                "marketplace_id, credentials, status "
                "from platform_connections where platform='temu'"
            )
        )
    ).mappings().one()
    assert row["external_account_id"] == "1024"
    assert row["marketplace_id"] == "us"
    assert row["credentials"].startswith("enc:")
    assert row["status"] == "active"
    credentials = json.loads(decrypt_value(row["credentials"]))
    assert credentials["access_token"] == "temu-access-token-secret"
    assert credentials["expired_time"] == 1765634102

    listing = await client.get("/api/v1/platforms/connections", headers=headers)
    assert listing.status_code == 200
    assert "temu-access-token-secret" not in listing.text
    assert listing.json()["connections"][0]["platform"] == "temu"


@pytest.mark.asyncio
async def test_temu_manual_connect_validates_and_upserts_connection(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    headers = await _register(
        client,
        f"temu-manual-{uuid.uuid4().hex[:8]}@test.com",
    )

    async def fake_info(self, access_token, region):
        assert access_token == "manual-temu-token"
        assert region == "global"
        return {
            "mallId": 2048,
            "expiredTime": 1765634102,
            "apiScopeList": ["bg.order.list.v2.get"],
        }

    monkeypatch.setattr(
        temu_open_api.TemuOpenApiService,
        "get_token_info",
        fake_info,
    )

    for _ in range(2):
        response = await client.post(
            "/api/v1/platforms/temu/manual-connect",
            headers=headers,
            json={"access_token": "manual-temu-token", "region": "global"},
        )
        assert response.status_code == 200, response.text

    count = (
        await db_session.execute(
            text(
                "select count(*) from platform_connections "
                "where platform='temu' and external_account_id='2048'"
            )
        )
    ).scalar_one()
    assert count == 1

    tested = await client.post("/api/v1/platforms/temu/test", headers=headers)
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True
    assert tested.json()["mall_id"] == 2048


@pytest.mark.asyncio
async def test_temu_invalid_token_marks_connection_invalid(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_temu(monkeypatch)
    headers = await _register(
        client,
        f"temu-invalid-{uuid.uuid4().hex[:8]}@test.com",
    )

    async def valid_info(self, access_token, region):
        return {"mallId": 4096, "expiredTime": 1765634102, "apiScopeList": []}

    monkeypatch.setattr(
        temu_open_api.TemuOpenApiService,
        "get_token_info",
        valid_info,
    )
    connected = await client.post(
        "/api/v1/platforms/temu/manual-connect",
        headers=headers,
        json={"access_token": "valid-token", "region": "us"},
    )
    assert connected.status_code == 200, connected.text

    async def invalid_info(self, access_token, region):
        raise ValueError("Temu 授权已失效")

    monkeypatch.setattr(
        temu_open_api.TemuOpenApiService,
        "get_token_info",
        invalid_info,
    )
    tested = await client.post("/api/v1/platforms/temu/test", headers=headers)
    assert tested.status_code == 400

    status = (
        await db_session.execute(
            text(
                "select status from platform_connections "
                "where platform='temu' and external_account_id='4096'"
            )
        )
    ).scalar_one()
    assert status == "invalid"


@pytest.mark.asyncio
async def test_temu_connect_requires_provider_config(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(provider_config.settings, "TEMU_APP_KEY", None, raising=False)
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_APP_SECRET",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        provider_config.settings,
        "TEMU_REDIRECT_URI",
        None,
        raising=False,
    )
    provider_config.clear_cache()
    headers = await _register(
        client,
        f"temu-missing-{uuid.uuid4().hex[:8]}@test.com",
    )

    response = await client.post(
        "/api/v1/platforms/temu/connect-url",
        headers=headers,
        json={"region": "us"},
    )
    assert response.status_code == 400
    assert "Temu" in response.json()["detail"]
