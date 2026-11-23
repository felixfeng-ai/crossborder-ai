"""公共图片托管服务与移动端发布接口测试。"""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.services.public_image_storage import (
    S3PublicImageStorage,
    publish_public_image_asset,
)
from app.services.workspaces import ensure_personal_workspace


class FakePublicStorage:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.objects: list[dict] = []

    async def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> str:
        self.objects.append(
            {"key": key, "data": data, "content_type": content_type}
        )
        return f"{self.base_url.rstrip('/')}/{key}"


async def _register(client, db_session, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@", 1)[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    await db_session.commit()
    return headers, user, workspace


@pytest.mark.asyncio
async def test_publish_public_image_uses_deterministic_cdn_key(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    storage_key = f"mobile/{workspace_id}/{user_id}/{asset_id}.webp"
    target = tmp_path / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"webp-image")
    asset = ImageAsset(
        id=asset_id,
        user_id=user_id,
        workspace_id=workspace_id,
        name="Main image",
        kind="upload",
        storage_key=storage_key,
        content_type="image/webp",
        width=800,
        height=800,
        file_size=10,
    )
    storage = FakePublicStorage("https://cdn.example.com")

    first = await publish_public_image_asset(asset, storage=storage)
    second = await publish_public_image_asset(asset, storage=storage)

    expected_key = f"{workspace_id}/{asset_id}.webp"
    assert first == second == (
        f"https://cdn.example.com/{expected_key}"
    )
    assert [item["key"] for item in storage.objects] == [
        expected_key,
        expected_key,
    ]
    assert storage.objects[0]["content_type"] == "image/webp"


def test_s3_public_storage_uses_cache_and_content_type():
    calls = []

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    storage = S3PublicImageStorage(
        client=FakeClient(),
        bucket="bucket",
        base_url="https://cdn.example.com",
        prefix="public/images",
    )
    storage._put_sync(
        "workspace/asset.webp",
        b"image",
        "image/webp",
    )
    assert calls[0]["Key"] == (
        "public/images/workspace/asset.webp"
    )
    assert calls[0]["ContentType"] == "image/webp"
    assert calls[0]["CacheControl"].startswith("public")


@pytest.mark.asyncio
async def test_mobile_publish_public_image_endpoint(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    from PIL import Image
    import io

    headers, _user, workspace = await _register(
        client,
        db_session,
        "public-image@example.com",
    )
    raw = io.BytesIO()
    Image.new("RGB", (96, 96), (20, 80, 180)).save(raw, format="JPEG")
    base = f"/api/mobile/v1/workspaces/{workspace.id}/assets/images"
    uploaded = await client.post(
        base,
        headers=headers,
        files={"file": ("main.jpg", raw.getvalue(), "image/jpeg")},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["id"]

    async def fake_publish(asset, *, storage=None):
        del storage
        return f"https://cdn.example.com/public/images/{asset.id}.webp"

    monkeypatch.setattr(
        "app.routers.mobile.publish_public_image_asset",
        fake_publish,
    )
    response = await client.post(
        f"{base}/{asset_id}/public-url",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["public_url"].startswith(
        "https://cdn.example.com/"
    )
    assert "/api/" not in response.json()["public_url"]


@pytest.mark.asyncio
async def test_mobile_public_image_endpoint_is_workspace_scoped(
    client: AsyncClient,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    first_headers, _first_user, first_workspace = await _register(
        client,
        db_session,
        "public-image-first@example.com",
    )
    second_headers, _second_user, second_workspace = await _register(
        client,
        db_session,
        "public-image-second@example.com",
    )
    from PIL import Image
    import io

    raw = io.BytesIO()
    Image.new("RGB", (96, 96), (180, 80, 20)).save(raw, format="JPEG")
    first_base = (
        f"/api/mobile/v1/workspaces/{first_workspace.id}/assets/images"
    )
    uploaded = await client.post(
        first_base,
        headers=first_headers,
        files={"file": ("private.jpg", raw.getvalue(), "image/jpeg")},
    )
    asset_id = uploaded.json()["id"]

    response = await client.post(
        f"/api/mobile/v1/workspaces/{second_workspace.id}/assets/images/"
        f"{asset_id}/public-url",
        headers=second_headers,
    )
    assert response.status_code == 404
