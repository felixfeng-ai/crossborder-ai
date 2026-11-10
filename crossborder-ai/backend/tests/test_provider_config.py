"""Admin-managed provider configuration and runtime cache behavior."""

import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.system_config import SystemConfig
from app.services import provider_config
from app.services.ai.deepseek import DeepSeekService
from app.models.image_generation_task import ImageGenerationTask


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_config.clear_cache()
    yield
    provider_config.clear_cache()


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


@pytest.mark.asyncio
async def test_admin_updates_encrypted_provider_and_service_uses_it(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register(client, "admin@veyaship.com")

    updated = await client.put(
        "/api/v1/settings/providers/deepseek",
        json={"api_key": "sk-db-secret-123456", "model": "deepseek-flash"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["configured"] is True
    assert "sk-db-secret-123456" not in updated.text

    row = (
        await db_session.execute(
            select(SystemConfig).where(
                SystemConfig.key == "provider:deepseek:api_key"
            )
        )
    ).scalar_one()
    assert row.value.startswith("enc:")

    await provider_config.refresh(db_session)
    assert provider_config.get("deepseek", "api_key") == "sk-db-secret-123456"
    assert provider_config.get("deepseek", "model") == "deepseek-flash"

    captured: dict = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers=None, json=None, **kwargs):
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                200,
                    request=httpx.Request("POST", url),
                json={"choices": [{"message": {"content": "ok"}}]},
            )

    monkeypatch.setattr(
        "app.services.ai.deepseek.httpx.AsyncClient",
        FakeClient,
    )
    result = await DeepSeekService().generate("system", "user", max_tokens=10)
    assert result == "ok"
    assert captured["headers"]["Authorization"] == "Bearer sk-db-secret-123456"
    assert captured["json"]["model"] == "deepseek-flash"


@pytest.mark.asyncio
async def test_provider_status_masks_secret(client: AsyncClient):
    headers = await _register(client, "admin@veyaship.com")
    response = await client.put(
        "/api/v1/settings/providers/onebound",
        json={"api_key": "onebound-secret-key", "api_secret": "onebound-secret"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    status = await client.get("/api/v1/settings/providers", headers=headers)
    assert status.status_code == 200, status.text
    data = status.json()["providers"]["onebound"]
    assert data["configured"] is True
    assert data["fields"]["api_key"].startswith("oneb")
    assert "****" in data["fields"]["api_key"]
    assert "****" in data["fields"]["api_secret"]
    assert "onebound-secret" not in status.text


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_providers(client: AsyncClient):
    headers = await _register(client, f"normal-{uuid.uuid4().hex[:6]}@example.com")
    response = await client.put(
        "/api/v1/settings/providers/deepseek",
        json={"api_key": "should-not-save"},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_justone_token_is_encrypted_and_masked(
    client: AsyncClient,
    db_session,
):
    headers = await _register(client, "admin@veyaship.com")
    token = "justone-secret-token-123456"

    updated = await client.put(
        "/api/v1/settings/providers/justone",
        json={"token": token},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert token not in updated.text

    row = (
        await db_session.execute(
            select(SystemConfig).where(SystemConfig.key == "provider:justone:token")
        )
    ).scalar_one()
    assert row.value.startswith("enc:")

    status = await client.get("/api/v1/settings/providers", headers=headers)
    assert status.status_code == 200
    assert status.json()["providers"]["justone"]["configured"] is True
    assert "****" in status.json()["providers"]["justone"]["fields"]["token"]
    assert token not in status.text


@pytest.mark.asyncio
async def test_aliyun_runtime_config_enables_image_task(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register(client, "admin@veyaship.com")
    monkeypatch.setattr(provider_config.settings, "ALIYUN_DASHSCOPE_API_KEY", None)
    monkeypatch.setattr(provider_config.settings, "REPLICATE_API_KEY", None)

    updated = await client.put(
        "/api/v1/settings/providers/aliyun",
        json={"api_key": "dashscope-runtime-key", "model": "wanx2.1-t2i-turbo"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    response = await client.post(
        "/api/v1/images/generate",
        json={"prompt": "runtime configured product photo", "num_outputs": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    task = (
        await db_session.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.id == uuid.UUID(response.json()["task_id"])
            )
        )
    ).scalar_one()
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_shopify_runtime_config_enables_oauth_connect(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register(client, "admin@veyaship.com")
    monkeypatch.setattr(provider_config.settings, "SHOPIFY_API_KEY", None)
    monkeypatch.setattr(provider_config.settings, "SHOPIFY_API_SECRET", None)
    monkeypatch.setattr(provider_config.settings, "SHOPIFY_REDIRECT_URI", None)

    updated = await client.put(
        "/api/v1/settings/providers/shopify",
        json={
            "api_key": "shopify-runtime-key",
            "api_secret": "shopify-runtime-secret",
            "redirect_uri": "https://example.com/api/v1/shopify/callback",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    connect = await client.post(
        "/api/v1/shopify/connect",
        json={"shop": "runtime-store"},
        headers=headers,
    )
    assert connect.status_code == 200, connect.text
    assert connect.json()["auth_url"].startswith(
        "https://runtime-store.myshopify.com/admin/oauth/authorize?"
    )
