"""AI 营销视频 Agent、渲染编排和多镜头合成。"""

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services import provider_config
from app.services.marketing_video_agent import (
    build_fallback_marketing_plan,
    estimate_marketing_plan_credits,
    generate_marketing_plan,
    parse_marketing_plan,
)
from app.services.marketing_video_executor import (
    _video_path,
    assemble_marketing_video,
    cancel_marketing_project,
    sync_marketing_video_projects,
)


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (480, 480), (190, 120, 75)).save(output, format="PNG")
    return output.getvalue()


async def _professional_user(db_session) -> User:
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    user.credits = 200
    await db_session.flush()
    return user


async def _seed_asset(db_session, tmp_path, monkeypatch) -> ImageAsset:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path / "images"))
    user = await _professional_user(db_session)
    asset_id = uuid.uuid4()
    storage_key = f"{user.id}/{asset_id}.png"
    path = tmp_path / "images" / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_image_bytes())
    asset = ImageAsset(
        id=asset_id,
        user_id=user.id,
        name="Terra Body Oil",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=480,
        height=480,
        file_size=path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


def test_fallback_presenter_plan_has_person_demo_and_product_lock():
    plan = build_fallback_marketing_plan(
        idea="让通勤族看到它有多方便",
        product_name="Terra Body Oil",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
    )

    assert plan["title"]
    assert plan["hook"]
    assert plan["cta"]
    assert len(plan["shots"]) == 3
    assert any("presenter" in shot["prompt"].lower() for shot in plan["shots"])
    assert all("logo" in shot["prompt"].lower() for shot in plan["shots"])
    assert plan["shots"][-1]["purpose"] == "cta"
    assert sum(shot["duration"] for shot in plan["shots"]) == 15


def test_parse_plan_accepts_markdown_json_and_normalizes_shot_order():
    raw = """
```json
{
  "title": "Morning routine",
  "audience": "busy professionals",
  "angle": "speed",
  "hook": "Three seconds is all it takes.",
  "script": "Meet the product that fits your morning.",
  "cta": "Shop now",
  "shots": [
    {"position": 2, "title": "Use", "purpose": "demo", "prompt": "presenter uses product", "duration": 5},
    {"position": 1, "title": "Hook", "purpose": "hook", "prompt": "hero product close-up", "duration": 5},
    {"position": 3, "title": "CTA", "purpose": "cta", "prompt": "clean product end frame", "duration": 5}
  ]
}
```
"""
    plan = parse_marketing_plan(raw)

    assert [shot["position"] for shot in plan["shots"]] == [1, 2, 3]
    assert plan["shots"][0]["title"] == "Hook"


@pytest.mark.asyncio
async def test_generate_marketing_plan_uses_structured_llm_output():
    async def fake_generator(system_prompt, user_prompt, **kwargs):
        assert "cross-border ecommerce" in system_prompt
        assert "Terra" in user_prompt
        return json.dumps(
            {
                "title": "Terra morning routine",
                "audience": "busy professionals",
                "angle": "fast absorption",
                "hook": "Get dressed without the wait.",
                "script": "Show the product and demonstrate one benefit.",
                "cta": "Discover Terra",
                "shots": [
                    {"position": 1, "title": "Hook", "purpose": "hook", "prompt": "hero shot", "duration": 5},
                    {"position": 2, "title": "Presenter", "purpose": "presenter", "prompt": "presenter holds product", "duration": 5},
                    {"position": 3, "title": "CTA", "purpose": "cta", "prompt": "product end frame", "duration": 5},
                ],
            }
        )

    plan = await generate_marketing_plan(
        idea="show morning routine",
        product_name="Terra",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        text_generator=fake_generator,
    )

    assert plan["title"] == "Terra morning routine"
    assert plan["shots"][1]["purpose"] == "presenter"
    assert "PRODUCT CONSISTENCY LOCK" in plan["shots"][0]["prompt"]


@pytest.mark.asyncio
async def test_generate_marketing_plan_falls_back_on_bad_llm_output():
    async def fake_generator(system_prompt, user_prompt, **kwargs):
        return "not json"

    plan = await generate_marketing_plan(
        idea="show morning routine",
        product_name="Terra",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        text_generator=fake_generator,
    )

    assert len(plan["shots"]) == 3
    assert plan["shots"][-1]["purpose"] == "cta"


def test_marketing_plan_credit_estimate_counts_every_shot():
    plan = build_fallback_marketing_plan(
        idea="show the product",
        product_name="Terra",
        platform="tiktok",
        market="US",
        language="en",
        duration=20,
        template_id="feature_focus",
    )
    credits = estimate_marketing_plan_credits(
        plan,
        model="MiniMax-H3-Lite",
        resolution="480P",
    )
    assert len(plan["shots"]) == 4
    assert credits >= 40


def test_assemble_marketing_video_normalizes_for_browser_playback(
    tmp_path,
    monkeypatch,
):
    segments = []
    for index in range(2):
        path = tmp_path / f"shot-{index}.mp4"
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + bytes([index]))
        segments.append(path)
    output = tmp_path / "final.mp4"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42final")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )
    assemble_marketing_video(segments, output, segment_durations=[4, 4])

    assert output.is_file()
    assert len(calls) == 1
    assert "libx264" in calls[0]
    assert "yuv420p" in calls[0]
    assert "aac" in calls[0]
    assert "copy" not in calls[0]
    assert not list(tmp_path.glob("veyaship-concat-*.txt"))


def test_assemble_marketing_video_uses_visual_and_audio_crossfade(
    tmp_path,
    monkeypatch,
):
    segments = []
    for index in range(3):
        path = tmp_path / f"shot-{index}.mp4"
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + bytes([index]))
        segments.append(path)
    output = tmp_path / "final-crossfade.mp4"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42crossfade")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )
    assemble_marketing_video(
        segments,
        output,
        segment_durations=[4, 4, 3],
    )

    assert output.is_file()
    assert len(calls) == 1
    command = " ".join(calls[0])
    assert "xfade=transition=fade" in command
    assert "acrossfade=d=0.20" in command
    assert "concat" not in command


def test_assemble_marketing_video_rejects_failed_normalization(
    tmp_path,
    monkeypatch,
):
    segment = tmp_path / "shot.mp4"
    segment.write_bytes(b"\x00\x00\x00\x18ftypmp42shot")
    output = tmp_path / "final.mp4"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )
    with pytest.raises(ValueError, match="标准化失败"):
        assemble_marketing_video([segment], output)

    assert len(calls) == 1
    assert "libx264" in calls[0]
    assert not output.exists()


def test_assemble_marketing_video_requires_durations_for_multiple_shots(
    tmp_path,
):
    segments = []
    for index in range(2):
        path = tmp_path / f"shot-{index}.mp4"
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        segments.append(path)

    with pytest.raises(ValueError, match="镜头时长"):
        assemble_marketing_video(segments, tmp_path / "final.mp4")


def test_assemble_marketing_video_burns_valid_subtitles(
    tmp_path,
    monkeypatch,
):
    segment = tmp_path / "shot.mp4"
    segment.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    subtitle = tmp_path / "shot.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\n产品展示\n", encoding="utf-8")
    output = tmp_path / "final-subtitle.mp4"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42subtitle")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )

    assert assemble_marketing_video(
        [segment],
        output,
        subtitle_path=subtitle,
    ) is True
    assert output.is_file()
    assert len(calls) == 2
    assert "subtitles=" in " ".join(calls[1])


def test_assemble_marketing_video_rejects_missing_subtitle(
    tmp_path,
):
    segment = tmp_path / "shot.mp4"
    segment.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    with pytest.raises(ValueError, match="字幕文件不存在"):
        assemble_marketing_video(
            [segment],
            tmp_path / "final.mp4",
            subtitle_path=tmp_path / "missing.srt",
        )


def test_assemble_marketing_video_rejects_bad_inputs(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="没有可合成"):
        assemble_marketing_video([], tmp_path / "final.mp4")
    with pytest.raises(ValueError, match="文件不存在"):
        assemble_marketing_video(
            [tmp_path / "missing.mp4"],
            tmp_path / "final.mp4",
        )
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="路径非法"):
        _video_path("../outside.mp4")


@pytest.mark.asyncio
async def test_create_marketing_project_generates_brief_without_render(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    provider_config.clear_cache()

    response = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "让通勤族看到它有多方便",
            "product_name": "Terra Body Oil",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "duration": 15,
            "template_id": "presenter_demo",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "brief_ready"
    assert len(body["brief"]["shots"]) == 3
    await db_session.refresh(user)
    assert user.credits == 199
    task_count = await db_session.scalar(
        select(func.count()).select_from(VideoGenerationTask)
    )
    assert task_count == 0


@pytest.mark.asyncio
async def test_render_marketing_project_creates_shot_tasks_and_deducts_credits(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    provider_config.clear_cache()

    created = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "让通勤族看到它有多方便",
            "product_name": "Terra Body Oil",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "duration": 15,
            "template_id": "presenter_demo",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )
    project_id = created.json()["id"]
    submitted = []

    async def fake_submit(**kwargs):
        submitted.append(kwargs["prompt"])
        return f"provider-shot-{len(submitted)}"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )
    rendered = await client.post(
        f"/api/v1/marketing-videos/projects/{project_id}/render",
        headers=auth_headers,
    )

    assert rendered.status_code == 202, rendered.text
    body = rendered.json()
    assert body["status"] == "rendering"
    assert len(body["shots"]) == 3
    assert len(submitted) == 3
    task_count = await db_session.scalar(
        select(func.count()).select_from(VideoGenerationTask)
    )
    assert task_count == 3
    await db_session.refresh(user)
    assert user.credits == 199 - body["credits_charged"]


@pytest.mark.asyncio
async def test_render_rejects_insufficient_credits_without_provider_call(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    provider_config.clear_cache()
    created = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "show the product",
            "product_name": "Terra",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "duration": 15,
            "template_id": "presenter_demo",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )
    user.credits = 0
    await db_session.flush()
    called = False

    async def fake_submit(**kwargs):
        nonlocal called
        called = True
        return "should-not-run"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )
    response = await client.post(
        f"/api/v1/marketing-videos/projects/{created.json()['id']}/render",
        headers=auth_headers,
    )

    assert response.status_code == 402
    assert called is False


@pytest.mark.asyncio
async def test_marketing_project_user_isolation(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    provider_config.clear_cache()
    created = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "show the product",
            "product_name": "Terra",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "duration": 15,
            "template_id": "presenter_demo",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"marketing-other-{uuid.uuid4().hex[:6]}@example.com",
            "username": "marketing-other",
            "password": "testpass123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    response = await client.get(
        f"/api/v1/marketing-videos/projects/{created.json()['id']}",
        headers=other_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sync_marketing_project_assembles_completed_shots(
    db_session,
    tmp_path,
    monkeypatch,
    auth_headers,
):
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path / "videos"))
    project = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Terra campaign",
        product_name="Terra Body Oil",
        idea="show the product",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="rendering",
        brief_json="{}",
        credits_estimated=30,
        credits_charged=30,
    )
    db_session.add(project)
    await db_session.flush()

    for position in range(1, 4):
        task = VideoGenerationTask(
            user_id=user.id,
            source_asset_id=None,
            provider="minimax",
            model="MiniMax-H3-Lite",
            resolution="480P",
            duration=5,
            ratio="9:16",
            prompt=f"shot-{position}",
            status="succeeded",
            storage_key=f"{user.id}/shot-{position}.mp4",
            created_at=datetime.now(timezone.utc),
        )
        storage_path = tmp_path / "videos" / task.storage_key
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + bytes([position]))
        db_session.add(task)
        await db_session.flush()
        db_session.add(
            MarketingVideoShot(
                project_id=project.id,
                position=position,
                title=f"Shot {position}",
                purpose="demo",
                prompt=f"shot-{position}",
                duration=5,
                status="succeeded",
                video_task_id=task.id,
            )
        )
    await db_session.flush()

    def fake_assemble(
        segment_paths,
        output_path,
        subtitle_path=None,
        segment_durations=None,
    ):
        assert len(segment_paths) == 3
        assert subtitle_path is not None
        assert segment_durations == [5, 5, 5]
        assert subtitle_path.is_file()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42final")
        return True

    monkeypatch.setattr(
        "app.services.marketing_video_executor.assemble_marketing_video",
        fake_assemble,
    )
    count = await sync_marketing_video_projects(db_session)
    await db_session.refresh(project)

    assert count == 1
    assert project.status == "succeeded"
    assert project.final_storage_key
    assert (tmp_path / "videos" / project.final_storage_key).is_file()


@pytest.mark.asyncio
async def test_marketing_project_only_exposes_existing_video_file(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path / "videos"))
    storage_key = f"{user.id}/marketing-file-check.mp4"
    final_path = tmp_path / "videos" / storage_key
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"\x00\x00\x00\x18ftypmp42final")
    project = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="File availability",
        product_name="Terra",
        idea="check file",
        platform="tiktok",
        market="US",
        language="en",
        duration=4,
        template_id="professional_script",
        mode="script",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="succeeded",
        brief_json="{}",
        credits_estimated=10,
        credits_charged=10,
        final_storage_key=storage_key,
    )
    db_session.add(project)
    await db_session.flush()

    available = await client.get(
        f"/api/v1/marketing-videos/projects/{project.id}",
        headers=auth_headers,
    )
    assert available.status_code == 200
    assert available.json()["video_available"] is True
    assert available.json()["final_video_url"].endswith("/file")

    file_response = await client.get(
        f"/api/v1/marketing-videos/projects/{project.id}/file",
        headers=auth_headers,
    )
    assert file_response.status_code == 200
    disposition = file_response.headers["content-disposition"]
    assert "Terra-tiktok" in disposition
    assert ".mp4" in disposition

    final_path.unlink()
    missing = await client.get(
        f"/api/v1/marketing-videos/projects/{project.id}",
        headers=auth_headers,
    )
    assert missing.status_code == 200
    assert missing.json()["video_available"] is False
    assert missing.json()["final_video_url"] is None

    file_response = await client.get(
        f"/api/v1/marketing-videos/projects/{project.id}/file",
        headers=auth_headers,
    )
    assert file_response.status_code == 404
    assert "文件缺失" in file_response.json()["detail"]


@pytest.mark.asyncio
async def test_sync_marks_project_failed_when_any_shot_fails(
    db_session,
    tmp_path,
    monkeypatch,
    auth_headers,
):
    user = await _professional_user(db_session)
    user.credits = 100
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path / "videos"))
    project = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Failed campaign",
        product_name="Terra Body Oil",
        idea="show the product",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="rendering",
        brief_json="{}",
        credits_estimated=30,
        credits_charged=30,
    )
    db_session.add(project)
    await db_session.flush()
    failed_task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=5,
        ratio="9:16",
        prompt="failed",
        status="failed",
        error="审核失败",
    )
    db_session.add(failed_task)
    await db_session.flush()
    db_session.add(
        MarketingVideoShot(
            project_id=project.id,
            position=1,
            title="Failed shot",
            purpose="demo",
            prompt="failed",
            duration=5,
            status="failed",
            video_task_id=failed_task.id,
        )
    )
    await db_session.flush()

    await sync_marketing_video_projects(db_session)
    await db_session.refresh(project)

    assert project.status == "failed"
    assert project.error == "审核失败"
    assert project.credits_refunded == 30
    await db_session.refresh(user)
    assert user.credits == 130


@pytest.mark.asyncio
async def test_cancel_marketing_project_before_and_during_render(
    db_session,
    auth_headers,
    monkeypatch,
):
    user = await _professional_user(db_session)
    draft = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Draft campaign",
        product_name="Terra",
        idea="idea",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="brief_ready",
        brief_json="{}",
    )
    rendering = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Rendering campaign",
        product_name="Terra",
        idea="idea",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="rendering",
        brief_json="{}",
    )
    db_session.add_all([draft, rendering])
    await db_session.flush()
    running_task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=5,
        ratio="9:16",
        prompt="running",
        provider_task_id="provider-running",
        status="running",
    )
    db_session.add(running_task)
    await db_session.flush()
    shot = MarketingVideoShot(
        project_id=rendering.id,
        position=1,
        title="Shot",
        purpose="hook",
        prompt="running",
        duration=5,
        status="running",
        video_task_id=running_task.id,
    )
    db_session.add(shot)
    await db_session.flush()

    async def fake_cancel(db, task):
        task.status = "canceled"
        await db.flush()
        return True

    monkeypatch.setattr(
        "app.services.marketing_video_executor.cancel_video_task",
        fake_cancel,
    )

    assert await cancel_marketing_project(db_session, draft) is True
    assert await cancel_marketing_project(db_session, rendering) is True
    await db_session.refresh(shot)
    assert draft.status == "canceled"
    assert rendering.status == "canceled"
    assert shot.status == "canceled"
