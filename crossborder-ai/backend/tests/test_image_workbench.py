"""图片工作台：上传、素材隔离、平台尺寸和白底处理。"""

import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.services.image_processing import normalize_uploaded_image


def _png_bytes(size=(120, 80), transparent=True) -> bytes:
    mode = "RGBA" if transparent else "RGB"
    color = (220, 40, 40, 255) if transparent else (220, 40, 40)
    image = Image.new(mode, size, color)
    if transparent:
        # 留出透明边，验证白底合成确实发生。
        image.paste((0, 0, 0, 0), (0, 0, size[0] // 2, size[1]))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _jpeg_bytes(size=(640, 480)) -> bytes:
    image = Image.new("RGB", size, (220, 40, 40))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def test_normalize_jpeg_uses_rgb_webp_without_alpha():
    normalized, width, height = normalize_uploaded_image(
        _jpeg_bytes(),
        12 * 1024 * 1024,
    )

    assert (width, height) == (640, 480)
    output = Image.open(io.BytesIO(normalized))
    assert output.format == "WEBP"
    assert output.mode == "RGB"


async def _upload(
    client: AsyncClient,
    headers: dict,
    *,
    filename: str = "product.png",
    content: bytes | None = None,
    content_type: str = "image/png",
):
    return await client.post(
        "/api/v1/images/assets/upload",
        files={"file": (filename, content or _png_bytes(), content_type)},
        headers=headers,
    )


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
async def test_upload_persists_user_asset_and_serves_file(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))

    response = await _upload(client, auth_headers)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["kind"] == "upload"
    assert data["width"] == 120
    assert data["height"] == 80
    assert data["image_url"].endswith(f"/images/assets/{data['id']}/file")

    asset = (
        await db_session.execute(
            select(ImageAsset).where(ImageAsset.id == uuid.UUID(data["id"]))
        )
    ).scalar_one()
    assert (tmp_path / asset.storage_key).exists()

    file_response = await client.get(data["image_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("image/")


@pytest.mark.asyncio
async def test_upload_rejects_non_image(
    client: AsyncClient,
    auth_headers: dict,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))

    response = await _upload(
        client,
        auth_headers,
        filename="fake.png",
        content=b"not an image",
    )

    assert response.status_code == 400
    assert "图片" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_presets_contains_cross_border_platforms(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/images/presets", headers=auth_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert {"amazon-main", "shopify-product", "temu-main", "shein-main"} <= ids


@pytest.mark.asyncio
async def test_white_background_processing_uses_preset_dimensions(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    uploaded = await _upload(client, auth_headers)
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["id"]

    response = await client.post(
        f"/api/v1/images/assets/{asset_id}/process",
        json={"preset_id": "temu-main"},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    processed = response.json()
    assert processed["kind"] == "processed"
    assert processed["width"] == 1200
    assert processed["height"] == 1200
    assert processed["preset_id"] == "temu-main"

    file_response = await client.get(processed["image_url"])
    output = Image.open(io.BytesIO(file_response.content)).convert("RGB")
    assert output.size == (1200, 1200)
    assert output.getpixel((0, 0)) == (255, 255, 255)

    source = (
        await db_session.execute(
            select(ImageAsset).where(ImageAsset.id == uuid.UUID(asset_id))
        )
    ).scalar_one()
    assert source.user_id is not None


@pytest.mark.asyncio
async def test_other_user_cannot_process_or_delete_asset(
    client: AsyncClient,
    auth_headers: dict,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    uploaded = await _upload(client, auth_headers)
    asset_id = uploaded.json()["id"]
    other_headers = await _register(client, f"other-{uuid.uuid4().hex[:6]}@example.com")

    process = await client.post(
        f"/api/v1/images/assets/{asset_id}/process",
        json={"preset_id": "amazon-main"},
        headers=other_headers,
    )
    delete = await client.delete(
        f"/api/v1/images/assets/{asset_id}",
        headers=other_headers,
    )

    assert process.status_code == 404
    assert delete.status_code == 404
