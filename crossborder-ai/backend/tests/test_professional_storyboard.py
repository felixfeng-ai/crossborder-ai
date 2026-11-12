"""专业脚本分镜解析、创建与短镜头裁切测试。"""

import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services import provider_config
from app.services.professional_storyboard import (
    build_shot_prompt,
    parse_professional_storyboard,
    provider_render_duration,
)
from app.services.marketing_video_executor import trim_video_segment


SCRIPT = """专业分镜脚本
一、保持视频主体、动作节奏、镜头顺序和画面构图一致，不确定的信息不要编造。

分镜 1｜00:00–00:04｜门口的快递（时长 4 秒）
冬日清晨，一只牛皮纸快递箱放在门垫上，箱面落着雪花。无对白、无字幕、无水印。

分镜 2｜00:04–00:08｜拆开纸箱（时长 4 秒）
俯拍，一双手划开快递箱封口，露出带有 DONMIS 品牌 LOGO 的香薰片礼盒。无对白、无字幕。

分镜 3｜00:08–00:12｜取出礼盒端详（时长 4 秒）
近景，金发女性双手捧起礼盒端详，背景是虚化的客厅与圣诞树。无对白。

分镜 4｜00:12–00:16｜检查与轻嗅（时长 4 秒）
特写，她打开礼盒，取出圆形香薰片凑近轻嗅。无对白。

分镜 5｜00:16–00:20｜准备包装材料（时长 4 秒）
俯拍，木桌上整齐摆放包装纸、淡紫色缎带、松枝松果和干橙片。无对白。

分镜 6｜00:20–00:24｜装点礼盒（时长 4 秒）
特写，她给礼盒固定松枝松果、干橙片与肉桂棒。无对白。

分镜 7｜00:24–00:27｜摆到圣诞树下（时长 3 秒）
中景，她把礼盒摆到圣诞树下，正面朝外。无对白。

分镜 8｜00:27–00:30｜收尾微笑（时长 3 秒）
中景，她站在圣诞树前望向礼盒微笑，窗外有雪花。无对白。

三、生成约束
1. 按时间顺序完成镜头衔接，保持人物、物体和场景一致。
2. 视频全程无对白，依赖画面剪辑和音乐营造氛围。
3. 无字幕、无水印。
"""


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (480, 480), (190, 120, 75)).save(output, format="PNG")
    return output.getvalue()


async def _professional_user(db_session) -> User:
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
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
        name="DONMIS 香薰礼盒",
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


def test_parser_preserves_eight_shots_and_exact_timing():
    storyboard = parse_professional_storyboard(SCRIPT)

    assert storyboard.shot_count == 8
    assert storyboard.total_duration == 30
    assert [shot.duration for shot in storyboard.shots] == [
        4, 4, 4, 4, 4, 4, 3, 3,
    ]
    assert storyboard.shots[0].position == 1
    assert storyboard.shots[0].start_seconds == 0
    assert storyboard.shots[-1].end_seconds == 30
    assert storyboard.shots[0].title == "门口的快递"
    assert "牛皮纸快递箱" in storyboard.shots[0].source_text
    assert storyboard.no_dialogue is True
    assert storyboard.no_subtitles is True
    assert storyboard.no_watermark is True
    assert "保持人物、物体和场景一致" in storyboard.global_constraints


def test_parser_rejects_timecode_mismatch():
    broken = SCRIPT.replace(
        "分镜 2｜00:04–00:08｜拆开纸箱（时长 4 秒）",
        "分镜 2｜00:05–00:09｜拆开纸箱（时长 4 秒）",
    )
    with pytest.raises(ValueError, match="时间码"):
        parse_professional_storyboard(broken)


def test_provider_render_duration_uses_model_minimum():
    assert provider_render_duration("MiniMax-H3-Lite", 3) == 4
    assert provider_render_duration("MiniMax-H3-Lite", 7) == 7


def test_shot_prompt_contains_adjacent_shot_boundaries_and_reference_roles():
    storyboard = parse_professional_storyboard(SCRIPT)
    prompt = build_shot_prompt(
        storyboard.shots[1],
        product_name="DONMIS 圣诞香薰礼盒",
        global_constraints=storyboard.global_constraints,
        no_dialogue=storyboard.no_dialogue,
        no_subtitles=storyboard.no_subtitles,
        no_watermark=storyboard.no_watermark,
        previous_shot=storyboard.shots[0],
        next_shot=storyboard.shots[2],
        reference_assets=[
            {"asset_id": "primary", "role": "front", "is_primary": True},
            {"asset_id": "package", "role": "package", "is_primary": False},
            {"asset_id": "detail", "role": "detail", "is_primary": False},
        ],
    )

    assert "PREVIOUS SHOT BOUNDARY" in prompt
    assert "NEXT SHOT BOUNDARY" in prompt
    assert "门口的快递" in prompt
    assert "取出礼盒端详" in prompt
    assert "PRODUCT REFERENCE IMAGE MAP" in prompt
    assert "package" in prompt
    assert "Reference image 3" in prompt


def test_trim_video_segment_uses_exact_target_duration(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    output = tmp_path / "trimmed.mp4"
    source.write_bytes(b"\x00\x00\x00\x18ftypmp42source")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        output.write_bytes(b"\x00\x00\x00\x18ftypmp42trimmed")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )
    trim_video_segment(source, output, 3)

    assert output.is_file()
    assert calls
    assert "3" in calls[0]
    assert "-t" in calls[0]


def test_trim_video_segment_rejects_missing_file_and_zero_duration(tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        trim_video_segment(
            tmp_path / "missing.mp4",
            tmp_path / "output.mp4",
            3,
        )

    source = tmp_path / "source.mp4"
    source.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    with pytest.raises(ValueError, match="大于 0"):
        trim_video_segment(source, tmp_path / "output.mp4", 0)


@pytest.mark.asyncio
async def test_storyboard_preview_and_create_preserve_shots_without_plan_charge(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    preview = await client.post(
        "/api/v1/marketing-videos/storyboards/preview",
        json={"script": SCRIPT},
        headers=auth_headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["shot_count"] == 8
    assert preview.json()["total_duration"] == 30

    created = await client.post(
        "/api/v1/marketing-videos/storyboards/projects",
        json={
            "source_asset_id": str(asset.id),
            "product_name": "DONMIS 圣诞香薰礼盒",
            "script": SCRIPT,
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["mode"] == "script"
    assert body["duration"] == 30
    assert len(body["shots"]) == 8
    assert body["shots"][0]["source_text"].startswith("冬日清晨")
    assert body["shots"][-1]["duration"] == 3
    assert body["subtitle_url"] is None
    await db_session.refresh(user)
    assert user.credits == 200


@pytest.mark.asyncio
async def test_storyboard_project_accepts_nine_product_reference_images(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    primary = await _seed_asset(db_session, tmp_path, monkeypatch)
    references = []
    roles = [
        "front",
        "back",
        "detail",
        "package",
        "structure",
        "logo",
        "scale",
        "lifestyle",
    ]
    for index, role in enumerate(roles):
        asset = await _seed_asset(db_session, tmp_path, monkeypatch)
        asset.name = f"商品参考图 {index + 1}"
        references.append({"asset_id": str(asset.id), "role": role})
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    created = await client.post(
        "/api/v1/marketing-videos/storyboards/projects",
        json={
            "source_asset_id": str(primary.id),
            "reference_assets": references,
            "product_name": "DONMIS 圣诞香薰礼盒",
            "script": SCRIPT,
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert len(body["reference_assets"]) == 9
    assert body["reference_assets"][0] == {
        "asset_id": str(primary.id),
        "role": "front",
        "is_primary": True,
    }
    assert body["reference_assets"][1] == {
        "asset_id": references[0]["asset_id"],
        "role": "front",
        "is_primary": False,
    }
    assert {item["role"] for item in body["reference_assets"]} == set(roles)


@pytest.mark.asyncio
async def test_storyboard_project_rejects_more_than_nine_product_images(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    primary = await _seed_asset(db_session, tmp_path, monkeypatch)
    references = []
    for _ in range(9):
        asset = await _seed_asset(db_session, tmp_path, monkeypatch)
        references.append({"asset_id": str(asset.id), "role": "detail"})
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    rejected = await client.post(
        "/api/v1/marketing-videos/storyboards/projects",
        json={
            "source_asset_id": str(primary.id),
            "reference_assets": references,
            "product_name": "DONMIS 圣诞香薰礼盒",
            "script": SCRIPT,
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )

    assert rejected.status_code == 400
    assert "9" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_storyboard_render_uses_provider_minimum_for_three_second_shots(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    created = await client.post(
        "/api/v1/marketing-videos/storyboards/projects",
        json={
            "source_asset_id": str(asset.id),
            "product_name": "DONMIS 圣诞香薰礼盒",
            "script": SCRIPT,
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    submitted = []

    async def fake_submit(**kwargs):
        submitted.append(kwargs["duration"])
        return f"provider-{len(submitted)}"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )
    rendered = await client.post(
        f"/api/v1/marketing-videos/projects/{created.json()['id']}/render",
        headers=auth_headers,
    )

    assert rendered.status_code == 202, rendered.text
    assert submitted == [4, 4, 4, 4, 4, 4, 4, 4]
    assert rendered.json()["shots"][-1]["duration"] == 3
    tasks = (
        await db_session.execute(select(VideoGenerationTask))
    ).scalars().all()
    assert [task.duration for task in tasks] == [4, 4, 4, 4, 4, 4, 4, 4]


@pytest.mark.asyncio
async def test_storyboard_render_passes_product_reference_images_to_provider(
    client,
    db_session,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    primary = await _seed_asset(db_session, tmp_path, monkeypatch)
    front = await _seed_asset(db_session, tmp_path, monkeypatch)
    detail = await _seed_asset(db_session, tmp_path, monkeypatch)
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    created = await client.post(
        "/api/v1/marketing-videos/storyboards/projects",
        json={
            "source_asset_id": str(primary.id),
            "reference_assets": [
                {"asset_id": str(front.id), "role": "front"},
                {"asset_id": str(detail.id), "role": "detail"},
            ],
            "product_name": "DONMIS 圣诞香薰礼盒",
            "script": SCRIPT,
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    submitted: list[dict] = []

    async def fake_submit(**kwargs):
        submitted.append(kwargs)
        return f"provider-ref-{len(submitted)}"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )
    rendered = await client.post(
        f"/api/v1/marketing-videos/projects/{created.json()['id']}/render",
        headers=auth_headers,
    )

    assert rendered.status_code == 202, rendered.text
    assert len(submitted) == 8
    assert all(len(item["reference_images"]) == 3 for item in submitted)
    assert all(item["first_frame"] is None for item in submitted)
