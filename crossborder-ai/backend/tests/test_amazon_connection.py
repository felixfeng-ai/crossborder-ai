"""Amazon SP-API 授权连接与凭据保护测试。"""

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.services import provider_config
from app.services import amazon_sp_api


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": email.split("@")[0], "password": "testpass123"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _configure_amazon(monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.asyncio
async def test_amazon_connect_url_contains_state(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    headers = await _register(client, f"amazon-url-{uuid.uuid4().hex[:8]}@test.com")

    response = await client.post(
        "/api/v1/platforms/amazon/connect-url",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    auth_url = response.json()["auth_url"]
    parsed = urlparse(auth_url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "sellercentral.amazon.com"
    assert query["application_id"] == ["amzn1.sp.solution.test"]
    assert query["state"][0]


@pytest.mark.asyncio
async def test_amazon_callback_stores_encrypted_connection(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_amazon(monkeypatch)
    headers = await _register(client, f"amazon-callback-{uuid.uuid4().hex[:8]}@test.com")
    connect = await client.post(
        "/api/v1/platforms/amazon/connect-url",
        headers=headers,
    )
    state = parse_qs(urlparse(connect.json()["auth_url"]).query)["state"][0]

    async def fake_exchange(self, code, redirect_uri):
        assert code == "spapi-code"
        assert redirect_uri.endswith("/callback")
        return {
            "refresh_token": "Atzr|amazon-refresh-token",
            "access_token": "Atza|amazon-access-token",
        }

    async def fake_participations(self, refresh_token):
        assert refresh_token == "Atzr|amazon-refresh-token"
        return [
            {
                "marketplace": {
                    "id": "ATVPDKIKX0DER",
                    "name": "Amazon.com",
                    "countryCode": "US",
                },
                "participation": {"isParticipating": True},
            }
        ]

    monkeypatch.setattr(
        amazon_sp_api.AmazonSpApiService,
        "exchange_authorization_code",
        fake_exchange,
    )
    monkeypatch.setattr(
        amazon_sp_api.AmazonSpApiService,
        "get_marketplace_participations",
        fake_participations,
    )

    callback = await client.get(
        "/api/v1/platforms/amazon/callback",
        params={
            "spapi_oauth_code": "spapi-code",
            "state": state,
            "selling_partner_id": "A1SELLER",
        },
        follow_redirects=False,
    )
    assert callback.status_code == 302, callback.text
    assert "amazon_connected=1" in callback.headers["location"]

    row = (
        await db_session.execute(
            text(
                "select platform, account_name, external_account_id, credentials, status "
                "from platform_connections where platform='amazon'"
            )
        )
    ).mappings().one()
    assert row["account_name"] == "Amazon.com"
    assert row["external_account_id"] == "A1SELLER"
    assert row["credentials"].startswith("enc:")
    assert row["status"] == "active"

    listing = await client.get("/api/v1/platforms/connections", headers=headers)
    assert listing.status_code == 200
    assert "Atzr|amazon-refresh-token" not in listing.text
    assert listing.json()["connections"][0]["platform"] == "amazon"

    tested = await client.post("/api/v1/platforms/amazon/test", headers=headers)
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True
    assert tested.json()["marketplaces"][0]["marketplace"]["id"] == "ATVPDKIKX0DER"


@pytest.mark.asyncio
async def test_amazon_connect_requires_app_config(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(provider_config.settings, "AMAZON_APP_ID", None, raising=False)
    monkeypatch.setattr(provider_config.settings, "AMAZON_CLIENT_ID", None, raising=False)
    monkeypatch.setattr(provider_config.settings, "AMAZON_CLIENT_SECRET", None, raising=False)
    monkeypatch.setattr(provider_config.settings, "AMAZON_REDIRECT_URI", None, raising=False)
    provider_config.clear_cache()
    headers = await _register(client, f"amazon-missing-{uuid.uuid4().hex[:8]}@test.com")

    response = await client.post(
        "/api/v1/platforms/amazon/connect-url",
        headers=headers,
    )
    assert response.status_code == 400
    assert "Amazon" in response.json()["detail"]
