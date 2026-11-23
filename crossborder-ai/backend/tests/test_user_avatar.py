"""用户头像上传、读取和移除。"""

import io

import pytest
from PIL import Image

from app.core.config import settings


def _avatar_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (640, 480), (32, 96, 180)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_user_can_upload_read_and_remove_avatar(
    client,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "AVATAR_STORAGE_DIR", str(tmp_path))
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "avatar-user@example.com",
            "username": "头像用户",
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}",
    }

    uploaded = await client.put(
        "/api/v1/users/me/avatar",
        headers=headers,
        files={"file": ("avatar.png", _avatar_png(), "image/png")},
    )

    assert uploaded.status_code == 200
    avatar_url = uploaded.json()["avatar_url"]
    assert avatar_url.startswith("/api/v1/users/me/avatar?u=")

    profile = await client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["avatar_url"] == avatar_url

    image = await client.get(avatar_url, headers=headers)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"
    assert image.content.startswith(b"RIFF")

    removed = await client.delete("/api/v1/users/me/avatar", headers=headers)
    assert removed.status_code == 204
    profile_after = await client.get("/api/v1/auth/me", headers=headers)
    assert profile_after.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_avatar_requires_login_and_rejects_non_image_content(
    client,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "AVATAR_STORAGE_DIR", str(tmp_path))
    anonymous = await client.get("/api/v1/users/me/avatar")
    assert anonymous.status_code == 401

    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "avatar-invalid@example.com",
            "username": "非法头像",
            "password": "testpass123",
        },
    )
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}",
    }
    rejected = await client.put(
        "/api/v1/users/me/avatar",
        headers=headers,
        files={"file": ("avatar.txt", b"not an image", "text/plain")},
    )
    assert rejected.status_code == 400
