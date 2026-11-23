"""私有图片与视频封面短时签名 URL 测试。"""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import settings
from app.models.video_generation_task import VideoGenerationTask
from app.models.workspace import Workspace
from app.services.workspaces import ensure_personal_workspace


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_private_image_file_requires_signed_url(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path / "images"))
    uploaded = await client.post(
        "/api/v1/images/assets/upload",
        files={
            "file": (
                "private.png",
                _image_bytes(),
                "image/png",
            )
        },
        headers=auth_headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    image_url = uploaded.json()["image_url"]
    path_without_token = image_url.split("?", 1)[0]

    anonymous = await client.get(path_without_token)
    signed = await client.get(image_url)

    assert "?token=" in image_url
    assert anonymous.status_code == 401
    assert signed.status_code == 200
    assert signed.content == _image_bytes() or signed.headers["content-type"] == "image/webp"


@pytest.mark.asyncio
async def test_video_thumbnail_requires_signed_url(
    client,
    auth_headers,
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.models.user import User
    from sqlalchemy import select

    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    storage_key = f"{user.id}/signed-thumbnail.mp4"
    video_path = Path(tmp_path) / storage_key
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    task = VideoGenerationTask(
        user_id=user.id,
        workspace_id=workspace.id,
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="signed thumbnail",
        status="succeeded",
        storage_key=storage_key,
    )
    db_session.add(task)
    await db_session.commit()
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path))

    def fake_thumbnail(_video_path):
        cover = Path(tmp_path) / "cover.jpg"
        cover.write_bytes(b"jpeg-cover")
        return cover

    monkeypatch.setattr(
        "app.routers.videos.ensure_video_thumbnail",
        fake_thumbnail,
    )
    history = await client.get(
        "/api/v1/videos/history",
        headers=auth_headers,
    )
    thumbnail_url = next(
        item["thumbnail_url"]
        for item in history.json()
        if item["id"] == str(task.id)
    )
    path_without_token = thumbnail_url.split("?", 1)[0]

    anonymous = await client.get(path_without_token)
    signed = await client.get(thumbnail_url)

    assert "?token=" in thumbnail_url
    assert anonymous.status_code == 401
    assert signed.status_code == 200
    assert signed.content == b"jpeg-cover"
