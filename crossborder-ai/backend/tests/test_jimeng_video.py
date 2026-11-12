"""即梦 / Seedance 方舟视频 Provider。"""

import base64
import io
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.marketing_video import MarketingVideoProject
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.routers.videos import video_capabilities
from app.services import provider_config
from app.services.jimeng_video import (
    build_jimeng_video_request,
    cancel_jimeng_video,
    download_jimeng_video,
    estimate_jimeng_cost_micros,
    estimate_jimeng_credits,
    get_jimeng_video_capabilities,
    parse_jimeng_submission,
    parse_jimeng_task,
    query_jimeng_video,
    submit_jimeng_video,
)


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (320, 320), (188, 140, 110)).save(output, format="PNG")
    return output.getvalue()


async def _professional_user(db_session) -> User:
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    user.credits = 300
    await db_session.flush()
    return user


async def _seed_asset(db_session, tmp_path, monkeypatch) -> ImageAsset:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user = await _professional_user(db_session)
    asset_id = uuid.uuid4()
    storage_key = f"{user.id}/{asset_id}.png"
    path = tmp_path / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_image_bytes())
    asset = ImageAsset(
        id=asset_id,
        user_id=user.id,
        name="Seedance Product",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=320,
        height=320,
        file_size=path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


def test_jimeng_request_encodes_first_frame_and_official_parameters():
    request = build_jimeng_video_request(
        api_key="ark-key",
        prompt="A premium product shot",
        model="doubao-seedance-2-0-260128",
        resolution="720P",
        duration=5,
        ratio="9:16",
        first_frame=b"image-bytes",
        first_frame_mime="image/png",
    )

    assert request.url.endswith("/contents/generations/tasks")
    assert request.headers["Authorization"] == "Bearer ark-key"
    assert request.body["model"] == "doubao-seedance-2-0-260128"
    assert request.body["resolution"] == "720p"
    assert request.body["duration"] == 5
    assert request.body["ratio"] == "9:16"
    assert request.body["watermark"] is False
    assert request.body["content"][1]["role"] == "first_frame"
    expected = base64.b64encode(b"image-bytes").decode("ascii")
    assert expected in request.body["content"][1]["image_url"]["url"]


def test_jimeng_request_supports_reference_images_and_rejects_too_many():
    request = build_jimeng_video_request(
        api_key="ark-key",
        prompt="Keep the same product with [图1] and [图2]",
        model="doubao-seedance-2-0-260128",
        resolution="1080P",
        duration=8,
        ratio="adaptive",
        reference_images=[
            (b"front", "image/png"),
            (b"detail", "image/jpeg"),
            (b"label", "image/webp"),
        ],
    )

    assert [item["role"] for item in request.body["content"][1:]] == [
        "reference_image",
        "reference_image",
        "reference_image",
    ]

    with pytest.raises(ValueError, match="最多支持 9 张"):
        build_jimeng_video_request(
            api_key="ark-key",
            prompt="product references",
            model="doubao-seedance-2-0-260128",
            resolution="720P",
            duration=5,
            ratio="9:16",
            reference_images=[(b"image", "image/png")] * 10,
        )


def test_jimeng_parser_normalizes_task_lifecycle():
    assert parse_jimeng_submission({"id": "task-1"}) == "task-1"
    assert parse_jimeng_task({"status": "queued"}) == {"status": "queued"}
    assert parse_jimeng_task({"status": "running"}) == {"status": "running"}
    assert parse_jimeng_task(
        {
            "status": "succeeded",
            "content": {"video_url": "https://cdn.example.com/video.mp4"},
            "duration": 5,
        }
    ) == {
        "status": "succeeded",
        "video_url": "https://cdn.example.com/video.mp4",
        "duration": 5,
    }
    failed = parse_jimeng_task(
        {
            "status": "failed",
            "error": {"code": "OutputVideoSensitiveContentDetected", "message": "审核失败"},
        }
    )
    assert failed["status"] == "failed"
    assert "审核失败" in failed["error"]
    assert parse_jimeng_task({"status": "cancelled"}) == {"status": "canceled"}
    assert parse_jimeng_task({"status": "expired"})["status"] == "failed"


def test_jimeng_capabilities_follow_configured_key():
    disabled = get_jimeng_video_capabilities(api_key="")
    enabled = get_jimeng_video_capabilities(api_key="ark-key")

    assert disabled["enabled"] is False
    assert enabled["enabled"] is True
    assert enabled["provider"] == "jimeng"
    assert {model["id"] for model in enabled["models"]} >= {
        "doubao-seedance-2-0-mini-260615",
        "doubao-seedance-2-0-fast-260128",
        "doubao-seedance-2-0-260128",
        "doubao-seedance-2-5-260628",
    }


def test_jimeng_validation_and_cost_estimates():
    assert estimate_jimeng_cost_micros(
        "doubao-seedance-2-0-260128",
        "720P",
        5,
    ) == 4_968_000
    assert estimate_jimeng_credits(
        "doubao-seedance-2-0-260128",
        "720P",
        5,
    ) == 95

    with pytest.raises(ValueError, match="提示词"):
        build_jimeng_video_request(
            api_key="key",
            prompt="",
            model="doubao-seedance-2-0-260128",
            resolution="720P",
            duration=5,
            ratio="9:16",
            first_frame=b"image",
            first_frame_mime="image/png",
        )
    with pytest.raises(ValueError, match="4-15"):
        build_jimeng_video_request(
            api_key="key",
            prompt="product",
            model="doubao-seedance-2-0-260128",
            resolution="720P",
            duration=3,
            ratio="9:16",
            first_frame=b"image",
            first_frame_mime="image/png",
        )
    with pytest.raises(ValueError, match="缺少商品图片"):
        build_jimeng_video_request(
            api_key="key",
            prompt="product",
            model="doubao-seedance-2-0-260128",
            resolution="720P",
            duration=5,
            ratio="9:16",
        )


def test_seedance_25_supports_thirty_seconds_and_thirty_references():
    request = build_jimeng_video_request(
        api_key="key",
        prompt="A thirty second premium product commercial",
        model="doubao-seedance-2-5-260628",
        resolution="1080P",
        duration=30,
        ratio="9:16",
        reference_images=[
            (b"image", "image/png")
            for _ in range(30)
        ],
    )
    assert request.body["duration"] == 30
    assert request.body["resolution"] == "1080p"
    assert len(request.body["content"]) == 31


@pytest.mark.asyncio
async def test_jimeng_http_lifecycle(monkeypatch):
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    provider_config.clear_cache()
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"jimeng-video"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/v3/contents/generations/tasks"
            assert request.headers["Authorization"] == "Bearer ark-key"
            return httpx.Response(200, json={"id": "task-123"})
        if request.method == "GET" and request.url.path.endswith("/tasks/task-123"):
            return httpx.Response(
                200,
                json={
                    "id": "task-123",
                    "status": "succeeded",
                    "content": {"video_url": "https://cdn.example.com/jimeng.mp4"},
                },
            )
        if request.method == "DELETE":
            assert request.url.path.endswith("/tasks/task-123")
            return httpx.Response(200, json={"deleted": True})
        if str(request.url) == "https://cdn.example.com/jimeng.mp4":
            return httpx.Response(200, content=mp4)
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.jimeng_video.httpx.AsyncClient",
        client_factory,
    )

    task_id = await submit_jimeng_video(
        prompt="product video",
        model="doubao-seedance-2-0-260128",
        resolution="720P",
        duration=5,
        ratio="9:16",
        first_frame=b"image-bytes",
        first_frame_mime="image/png",
    )
    queried = await query_jimeng_video(task_id)
    canceled = await cancel_jimeng_video(task_id)
    downloaded = await download_jimeng_video(queried["video_url"])

    assert task_id == "task-123"
    assert queried["status"] == "succeeded"
    assert canceled is True
    assert downloaded == mp4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "密钥无效"),
        (402, "余额不足"),
        (422, "审核"),
        (429, "频繁"),
        (500, "稍后重试"),
        (400, "请求参数"),
    ],
)
async def test_jimeng_submit_maps_provider_errors(
    monkeypatch,
    status_code,
    expected,
):
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    provider_config.clear_cache()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": "upstream"}},
        )

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.jimeng_video.httpx.AsyncClient",
        client_factory,
    )
    with pytest.raises(ValueError, match=expected):
        await submit_jimeng_video(
            prompt="product video",
            model="doubao-seedance-2-0-260128",
            resolution="720P",
            duration=5,
            ratio="9:16",
            first_frame=b"image-bytes",
            first_frame_mime="image/png",
        )


@pytest.mark.asyncio
async def test_jimeng_cancel_and_download_reject_invalid_responses(monkeypatch):
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    provider_config.clear_cache()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(404, json={"error": {"message": "gone"}})
        return httpx.Response(200, content=b"not-an-mp4")

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.jimeng_video.httpx.AsyncClient",
        client_factory,
    )

    assert await cancel_jimeng_video("missing-task") is False
    with pytest.raises(ValueError, match="不是有效 MP4"):
        await download_jimeng_video("https://cdn.example.com/bad.mp4")


@pytest.mark.asyncio
async def test_video_capabilities_hide_jimeng_until_configured(monkeypatch):
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "")
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "minimax-key")
    provider_config.clear_cache()
    disabled = await video_capabilities()
    assert "jimeng" not in {
        provider["provider"] for provider in disabled["providers"]
    }
    assert "seedance" not in {
        tier["id"] for tier in disabled["quality_tiers"]
    }

    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    provider_config.clear_cache()
    enabled = await video_capabilities()
    assert "jimeng" in {
        provider["provider"] for provider in enabled["providers"]
    }
    assert "seedance" in {
        tier["id"] for tier in enabled["quality_tiers"]
    }


@pytest.mark.asyncio
async def test_single_video_uses_jimeng_provider_without_minimax_key(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    provider_config.clear_cache()
    submitted = {}

    async def fake_submit(**kwargs):
        submitted.update(kwargs)
        return "jimeng-single-task"

    monkeypatch.setattr(
        "app.services.video_provider.submit_jimeng_video",
        fake_submit,
    )

    response = await client.post(
        "/api/v1/videos/generate",
        json={
            "source_asset_id": str(asset.id),
            "prompt": "premium product camera movement",
            "template_id": "clean_product",
            "quality_tier": "seedance",
            "style_preset": "commerce_showcase",
            "duration": 5,
            "ratio": "9:16",
        },
        headers=auth_headers,
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["provider"] == "jimeng"
    assert body["model"] == "doubao-seedance-2-0-260128"
    assert body["resolution"] == "720P"
    assert body["credits_cost"] == 95
    assert submitted["model"] == "doubao-seedance-2-0-260128"
    task = await db_session.get(
        VideoGenerationTask,
        uuid.UUID(body["id"]),
    )
    assert task is not None
    assert task.provider == "jimeng"
    await db_session.refresh(user)
    assert user.credits == 205


@pytest.mark.asyncio
async def test_marketing_project_saves_jimeng_provider_snapshot(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    provider_config.clear_cache()

    response = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "让用户看到商品的质感",
            "product_name": "Seedance Product",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "duration": 15,
            "template_id": "presenter_demo",
            "quality_tier": "seedance",
            "style_preset": "premium_luxury",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "jimeng"
    project = await db_session.get(
        MarketingVideoProject,
        uuid.UUID(body["id"]),
    )
    assert project is not None
    assert project.provider == "jimeng"


@pytest.mark.asyncio
async def test_professional_storyboard_uses_jimeng_render_duration_and_provider(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    monkeypatch.setattr(settings, "JIMENG_API_KEY", "ark-key")
    provider_config.clear_cache()

    response = await client.post(
        "/api/v1/marketing-videos/storyboards/projects",
        json={
            "source_asset_id": str(asset.id),
            "product_name": "Seedance Product",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "quality_tier": "seedance",
            "style_preset": "premium_luxury",
            "script": (
                "分镜 1｜00:00–00:04｜商品开场（时长 4 秒）\n"
                "产品置于暖光桌面中央，镜头缓慢推进，无对白、无字幕、无水印。\n\n"
                "分镜 2｜00:04–00:07｜细节展示（时长 3 秒）\n"
                "双手轻触商品材质，镜头平稳横移，无对白、无字幕、无水印。"
            ),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "jimeng"
    assert [shot["duration"] for shot in body["shots"]] == [4, 3]
    assert body["credits_estimated"] == 152
