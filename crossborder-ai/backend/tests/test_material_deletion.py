"""素材删除、权限和营销视频隔离测试。"""

import io
import uuid
from datetime import datetime, timezone

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (320, 320), (190, 120, 75)).save(output, format="PNG")
    return output.getvalue()


async def _user(db_session) -> User:
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.plan = "professional"
    user.credits = 800
    await db_session.flush()
    return user


async def _asset(db_session, tmp_path, monkeypatch) -> tuple[ImageAsset, str]:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path / "images"))
    user = await _user(db_session)
    asset_id = uuid.uuid4()
    storage_key = f"{user.id}/{asset_id}.webp"
    path = tmp_path / "images" / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_image_bytes())
    asset = ImageAsset(
        id=asset_id,
        user_id=user.id,
        name="素材",
        kind="upload",
        storage_key=storage_key,
        content_type="image/webp",
        width=320,
        height=320,
        file_size=path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    return asset, str(path)


@pytest.mark.asyncio
async def test_delete_generated_image_history_is_owner_and_terminal_only(
    client,
    db_session,
    auth_headers,
):
    user = await _user(db_session)
    completed = ImageGenerationTask(
        user_id=user.id,
        prompt="completed",
        num_outputs=1,
        status="completed",
        image_urls='["https://cdn.example.com/image.png"]',
    )
    running = ImageGenerationTask(
        user_id=user.id,
        prompt="running",
        num_outputs=1,
        status="processing",
        image_urls="[]",
    )
    db_session.add_all([completed, running])
    await db_session.flush()

    deleted = await client.delete(
        f"/api/v1/images/history/{completed.id}",
        headers=auth_headers,
    )
    protected = await client.delete(
        f"/api/v1/images/history/{running.id}",
        headers=auth_headers,
    )

    assert deleted.status_code == 204
    assert protected.status_code == 409
    assert await db_session.get(ImageGenerationTask, completed.id) is None
    assert await db_session.get(ImageGenerationTask, running.id) is not None


@pytest.mark.asyncio
async def test_video_history_excludes_marketing_shot_tasks(
    client,
    db_session,
    auth_headers,
):
    user = await _user(db_session)
    single = VideoGenerationTask(
        user_id=user.id,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="single",
        status="succeeded",
    )
    marketing_task = VideoGenerationTask(
        user_id=user.id,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="marketing",
        status="succeeded",
    )
    db_session.add_all([single, marketing_task])
    await db_session.flush()
    project = MarketingVideoProject(
        user_id=user.id,
        title="Campaign",
        product_name="Product",
        idea="idea",
        platform="tiktok",
        market="US",
        language="en",
        duration=4,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="succeeded",
        brief_json="{}",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        MarketingVideoShot(
            project_id=project.id,
            position=1,
            title="Shot",
            purpose="script",
            prompt="marketing",
            duration=4,
            status="succeeded",
            video_task_id=marketing_task.id,
        )
    )
    await db_session.flush()

    response = await client.get("/api/v1/videos/history", headers=auth_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(single.id)]


@pytest.mark.asyncio
async def test_delete_single_video_removes_file_and_protects_marketing_shot(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    user = await _user(db_session)
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path / "videos"))
    files = []
    tasks = []
    for index in range(2):
        task = VideoGenerationTask(
            user_id=user.id,
            provider="minimax",
            model="MiniMax-H3-Lite",
            resolution="480P",
            duration=4,
            ratio="9:16",
            prompt=f"video-{index}",
            status="succeeded",
            storage_key=f"{user.id}/video-{index}.mp4",
        )
        path = tmp_path / "videos" / task.storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        tasks.append(task)
        files.append(path)
    db_session.add_all(tasks)
    await db_session.flush()
    project = MarketingVideoProject(
        user_id=user.id,
        title="Campaign",
        product_name="Product",
        idea="idea",
        platform="tiktok",
        market="US",
        language="en",
        duration=4,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="succeeded",
        brief_json="{}",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        MarketingVideoShot(
            project_id=project.id,
            position=1,
            title="Shot",
            purpose="script",
            prompt="protected",
            duration=4,
            status="succeeded",
            video_task_id=tasks[1].id,
        )
    )
    await db_session.flush()

    deleted = await client.delete(
        f"/api/v1/videos/tasks/{tasks[0].id}",
        headers=auth_headers,
    )
    protected = await client.delete(
        f"/api/v1/videos/tasks/{tasks[1].id}",
        headers=auth_headers,
    )

    assert deleted.status_code == 204
    assert protected.status_code == 409
    assert not files[0].exists()
    assert files[1].exists()


@pytest.mark.asyncio
async def test_delete_marketing_project_removes_shots_tasks_and_files(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    user = await _user(db_session)
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path / "videos"))
    task = VideoGenerationTask(
        user_id=user.id,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="shot",
        status="succeeded",
        storage_key=f"{user.id}/shot.mp4",
    )
    db_session.add(task)
    await db_session.flush()
    task_path = tmp_path / "videos" / task.storage_key
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    project = MarketingVideoProject(
        user_id=user.id,
        title="Campaign",
        product_name="Product",
        idea="idea",
        platform="tiktok",
        market="US",
        language="en",
        duration=4,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="succeeded",
        brief_json="{}",
        final_storage_key=f"{user.id}/final.mp4",
    )
    db_session.add(project)
    await db_session.flush()
    final_path = tmp_path / "videos" / project.final_storage_key
    final_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    shot = MarketingVideoShot(
        project_id=project.id,
        position=1,
        title="Shot",
        purpose="script",
        prompt="shot",
        duration=4,
        status="succeeded",
        video_task_id=task.id,
    )
    db_session.add(shot)
    await db_session.flush()

    response = await client.delete(
        f"/api/v1/marketing-videos/projects/{project.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert await db_session.get(MarketingVideoProject, project.id) is None
    assert (
        await db_session.scalar(
            select(MarketingVideoShot).where(MarketingVideoShot.id == shot.id)
        )
    ) is None
    assert await db_session.get(VideoGenerationTask, task.id) is None
    assert not task_path.exists()
    assert not final_path.exists()
