"""移动端批量素材库排序、替换、删除和私有读取测试。"""

import io

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.user import User
from app.services.workspaces import ensure_personal_workspace


def _jpeg(color: tuple[int, int, int]) -> bytes:
    raw = io.BytesIO()
    image = Image.new("RGB", (96, 96), color)
    image.save(raw, format="JPEG", quality=90)
    return raw.getvalue()


async def _register(client, db_session, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@", 1)[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    await db_session.commit()
    return headers, workspace


@pytest.mark.asyncio
async def test_mobile_media_library_supports_order_replace_delete_and_private_file(
    client,
    db_session,
):
    headers, workspace = await _register(
        client,
        db_session,
        "media-library@example.com",
    )
    base = f"/api/mobile/v1/workspaces/{workspace.id}/assets/images"
    first = await client.post(
        base,
        headers=headers,
        files={"file": ("first.jpg", _jpeg((220, 50, 50)), "image/jpeg")},
    )
    second = await client.post(
        base,
        headers=headers,
        files={"file": ("second.jpg", _jpeg((50, 80, 220)), "image/jpeg")},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    assert first.json()["sort_order"] < second.json()["sort_order"]

    reordered = await client.put(
        f"{base}/reorder",
        headers=headers,
        json={"asset_ids": [second_id, first_id]},
    )
    listing = await client.get(base, headers=headers)
    assert reordered.status_code == 200
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [second_id, first_id]
    assert [item["sort_order"] for item in listing.json()] == [1, 2]

    replaced = await client.post(
        f"{base}/{second_id}/replace",
        headers=headers,
        files={
            "file": (
                "replacement.jpg",
                _jpeg((20, 160, 90)),
                "image/jpeg",
            )
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["id"] == second_id
    assert replaced.json()["name"] == "replacement"
    image_file = await client.get(
        f"{base}/{second_id}/file",
        headers=headers,
    )
    assert image_file.status_code == 200
    assert image_file.headers["content-type"].startswith("image/webp")

    deleted = await client.delete(
        f"{base}/{first_id}",
        headers=headers,
    )
    after_delete = await client.get(base, headers=headers)
    assert deleted.status_code == 200
    assert [item["id"] for item in after_delete.json()] == [second_id]
    # 软删除只移出素材库，历史 Listing 的图片地址仍可读取。
    historical_file = await client.get(
        f"{base}/{first_id}/file",
        headers=headers,
    )
    assert historical_file.status_code == 200


@pytest.mark.asyncio
async def test_mobile_media_file_is_workspace_private(client, db_session):
    owner_headers, workspace = await _register(
        client,
        db_session,
        "media-owner@example.com",
    )
    other_headers, _other_workspace = await _register(
        client,
        db_session,
        "media-other@example.com",
    )
    uploaded = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/assets/images",
        headers=owner_headers,
        files={"file": ("private.jpg", _jpeg((90, 90, 90)), "image/jpeg")},
    )
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["id"]

    response = await client.get(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/assets/images/{asset_id}/file"
        ),
        headers=other_headers,
    )

    assert response.status_code == 404
