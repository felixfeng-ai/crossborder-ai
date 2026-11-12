"""MiniMax H3 视频生成、异步任务和计费。"""

import io
import uuid
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services import provider_config
from app.services.minimax_video import (
    build_minimax_video_request,
    cancel_minimax_video,
    download_minimax_video,
    estimate_video_credits,
    get_minimax_video_capabilities,
    parse_minimax_task,
    parse_minimax_submission,
    query_minimax_video,
    submit_minimax_video,
    video_sha256,
)
from app.services.video_task_executor import poll_video_tasks


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (320, 320), (180, 140, 80)).save(output, format="PNG")
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
        name="首帧",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=320,
        height=320,
        file_size=path.stat().st_size,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


def test_video_capabilities_and_credits():
    capabilities = get_minimax_video_capabilities(api_key="test-key")
    assert capabilities["enabled"] is True
    assert capabilities["default_model"] == "MiniMax-H3-Lite"
    model = next(item for item in capabilities["models"] if item["id"] == "MiniMax-H3-Lite")
    assert "480P" in model["resolutions"]
    assert estimate_video_credits("MiniMax-H3-Lite", "480P", 4) == 12
    assert estimate_video_credits("MiniMax-H3-Lite", "768P", 4) == 18
    assert estimate_video_credits("MiniMax-H3", "2K", 4) == 60


def test_video_capabilities_disabled_without_key(monkeypatch):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    provider_config.clear_cache()
    capabilities = get_minimax_video_capabilities()
    assert capabilities["enabled"] is False


def test_image_to_video_request_uses_data_uri():
    request = build_minimax_video_request(
        api_key="secret",
        prompt="Slow product camera push-in",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        first_frame=_image_bytes(),
        first_frame_mime="image/png",
    )

    assert request.url.endswith("/v2/video_generation")
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.body["model"] == "MiniMax-H3-Lite"
    image_content = request.body["content"][1]
    assert image_content["type"] == "image_url"
    assert image_content["image_url"]["url"].startswith("data:image/png;base64,")
    assert "storage" not in image_content["image_url"]["url"]


def test_reference_video_request_supports_multiple_product_images():
    request = build_minimax_video_request(
        api_key="secret",
        prompt="Keep the same gift box from every angle",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        reference_images=[
            (_image_bytes(), "image/png"),
            (_image_bytes(), "image/png"),
            (_image_bytes(), "image/png"),
        ],
    )

    image_items = [
        item for item in request.body["content"] if item["type"] == "image_url"
    ]
    assert request.body["ratio"] == "9:16"
    assert len(image_items) == 3
    assert all(item["role"] == "reference_image" for item in image_items)
    assert not any(item["role"] == "first_frame" for item in image_items)


def test_reference_video_request_rejects_mixed_frame_and_reference_images():
    with pytest.raises(ValueError, match="不能同时"):
        build_minimax_video_request(
            api_key="secret",
            prompt="Product shot",
            model="MiniMax-H3-Lite",
            resolution="480P",
            duration=4,
            ratio="9:16",
            first_frame=_image_bytes(),
            first_frame_mime="image/png",
            reference_images=[(_image_bytes(), "image/png")],
        )


def test_reference_video_request_rejects_more_than_nine_images():
    with pytest.raises(ValueError, match="9"):
        build_minimax_video_request(
            api_key="secret",
            prompt="Product shot",
            model="MiniMax-H3-Lite",
            resolution="480P",
            duration=4,
            ratio="9:16",
            reference_images=[
                (_image_bytes(), "image/png")
                for _ in range(10)
            ],
        )


def test_invalid_video_selection_and_submission_payload():
    with pytest.raises(ValueError, match="缺少视频提示词"):
        build_minimax_video_request(
            api_key="secret",
            prompt=" ",
            model="MiniMax-H3-Lite",
            resolution="480P",
            duration=4,
            ratio="9:16",
            first_frame=_image_bytes(),
            first_frame_mime="image/png",
        )
    with pytest.raises(ValueError, match="不支持"):
        build_minimax_video_request(
            api_key="secret",
            prompt="product",
            model="MiniMax-H3-Lite",
            resolution="2K",
            duration=4,
            ratio="9:16",
            first_frame=_image_bytes(),
            first_frame_mime="image/png",
        )
    with pytest.raises(ValueError, match="任务 ID"):
        parse_minimax_submission({})
    with pytest.raises(ValueError, match="成片地址"):
        parse_minimax_task({"task": {"status": "succeeded", "content": {}}})
    with pytest.raises(ValueError, match="状态无法识别"):
        parse_minimax_task({"task": {"status": "unknown"}})


def test_parse_minimax_task_states():
    assert parse_minimax_task({"task": {"status": "queued"}}) == {"status": "queued"}
    succeeded = parse_minimax_task(
        {
            "task": {
                "status": "succeeded",
                "content": {"url": "https://example.com/video.mp4"},
                "duration": 4,
                "resolution": "480P",
                "ratio": "9:16",
            }
        }
    )
    assert succeeded["status"] == "succeeded"
    assert succeeded["video_url"] == "https://example.com/video.mp4"
    assert parse_minimax_task(
        {"task": {"status": "failed", "error": {"message": "审核失败"}}}
    )["error"] == "审核失败"


@pytest.mark.asyncio
async def test_minimax_http_lifecycle(monkeypatch):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"video-data"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/v2/video_generation"
            return httpx.Response(200, json={"task_id": "task-123"})
        if request.method == "GET" and request.url.path.startswith("/v2/query/"):
            return httpx.Response(
                200,
                json={
                    "task": {
                        "status": "succeeded",
                        "content": {"url": "https://cdn.example.com/video.mp4"},
                    }
                },
            )
        if request.method == "DELETE":
            return httpx.Response(200, json={"ok": True})
        if str(request.url) == "https://cdn.example.com/video.mp4":
            return httpx.Response(200, content=mp4)
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.minimax_video.httpx.AsyncClient",
        client_factory,
    )

    task_id = await submit_minimax_video(
        prompt="product video",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        first_frame=_image_bytes(),
        first_frame_mime="image/png",
    )
    queried = await query_minimax_video(task_id)
    canceled = await cancel_minimax_video(task_id)
    downloaded = await download_minimax_video(queried["video_url"])

    assert task_id == "task-123"
    assert queried["status"] == "succeeded"
    assert canceled is True
    assert downloaded == mp4
    assert len(video_sha256(downloaded)) == 64


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
async def test_minimax_submit_maps_provider_errors(
    monkeypatch,
    status_code,
    expected,
):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "upstream"}})

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.minimax_video.httpx.AsyncClient",
        client_factory,
    )
    with pytest.raises(ValueError, match=expected):
        await submit_minimax_video(
            prompt="product video",
            model="MiniMax-H3-Lite",
            resolution="480P",
            duration=4,
            ratio="9:16",
            first_frame=_image_bytes(),
            first_frame_mime="image/png",
        )


@pytest.mark.asyncio
async def test_download_rejects_invalid_mp4(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-an-mp4")

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.services.minimax_video.httpx.AsyncClient",
        client_factory,
    )
    with pytest.raises(ValueError, match="有效 MP4"):
        await download_minimax_video("https://cdn.example.com/bad.mp4")


@pytest.mark.asyncio
async def test_submit_video_task_deducts_credits_and_persists_provider_id(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    async def fake_submit(**kwargs):
        assert kwargs["model"] == "MiniMax-H3-Lite"
        assert kwargs["duration"] == 4
        return "minimax-task-1"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )

    response = await client.post(
        "/api/v1/videos/generate",
        json={
            "source_asset_id": str(asset.id),
            "prompt": "slow camera push in",
            "template_id": "clean_product",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
            "duration": 4,
            "ratio": "9:16",
        },
        headers=auth_headers,
    )

    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    task = (
        await db_session.execute(
            select(VideoGenerationTask).where(
                VideoGenerationTask.id == uuid.UUID(task_id)
            )
        )
    ).scalar_one()
    assert task.provider_task_id == "minimax-task-1"
    assert task.status == "running"
    await db_session.refresh(user)
    assert user.credits == 200 - task.credits_cost


@pytest.mark.asyncio
async def test_single_video_uses_quality_tier_and_structured_prompt(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    user.credits = 500
    await db_session.flush()
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    submitted = {}

    async def fake_submit(**kwargs):
        submitted.update(kwargs)
        return "minimax-quality-task"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )

    response = await client.post(
        "/api/v1/videos/generate",
        json={
            "source_asset_id": str(asset.id),
            "prompt": "一只手轻轻打开礼盒，露出内部香薰片",
            "template_id": "clean_product",
            "quality_tier": "standard",
            "style_preset": "premium_luxury",
            "duration": 4,
            "ratio": "9:16",
        },
        headers=auth_headers,
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["model"] == "MiniMax-H3-Highspeed"
    assert body["resolution"] == "768P"
    assert body["quality_tier"] == "standard"
    assert body["style_preset"] == "premium_luxury"
    assert body["credits_cost"] == 60
    assert submitted["model"] == "MiniMax-H3-Highspeed"
    assert submitted["resolution"] == "768P"
    assert "integrated_multimodal_description:" in submitted["prompt"]
    assert "overall_soundscape:" in submitted["prompt"]
    assert "一只手轻轻打开礼盒" in submitted["prompt"]
    await db_session.refresh(user)
    assert user.credits == 440


@pytest.mark.asyncio
async def test_insufficient_credits_does_not_submit_provider(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    user.credits = 0
    await db_session.flush()
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
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
        "/api/v1/videos/generate",
        json={
            "source_asset_id": str(asset.id),
            "prompt": "slow camera push in",
            "template_id": "clean_product",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
            "duration": 4,
            "ratio": "9:16",
        },
        headers=auth_headers,
    )

    assert response.status_code == 402
    assert called is False


@pytest.mark.asyncio
async def test_idempotency_key_prevents_duplicate_provider_submission(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    calls = 0

    async def fake_submit(**kwargs):
        nonlocal calls
        calls += 1
        return "minimax-idempotent"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )
    headers = {**auth_headers, "Idempotency-Key": "video-request-1"}
    payload = {
        "source_asset_id": str(asset.id),
        "prompt": "slow camera push in",
        "template_id": "clean_product",
        "model": "MiniMax-H3-Lite",
        "resolution": "480P",
        "duration": 4,
        "ratio": "9:16",
    }

    first = await client.post("/api/v1/videos/generate", json=payload, headers=headers)
    second = await client.post("/api/v1/videos/generate", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert calls == 1
    await db_session.refresh(user)
    assert user.credits == 200 - first.json()["credits_cost"]


@pytest.mark.asyncio
async def test_invalid_template_and_foreign_source_are_rejected(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    payload = {
        "source_asset_id": str(asset.id),
        "prompt": "slow camera push in",
        "template_id": "unknown",
        "model": "MiniMax-H3-Lite",
        "resolution": "480P",
        "duration": 4,
        "ratio": "9:16",
    }

    invalid_template = await client.post(
        "/api/v1/videos/generate",
        json=payload,
        headers=auth_headers,
    )
    other_email = f"video-source-{uuid.uuid4().hex[:6]}@example.com"
    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "username": "video-source-other",
            "password": "testpass123",
        },
    )
    other_user = (
        await db_session.execute(select(User).where(User.email == other_email))
    ).scalar_one()
    other_user.plan = "professional"
    other_user.credits = 200
    await db_session.flush()
    foreign_asset = await client.post(
        "/api/v1/videos/generate",
        json={**payload, "template_id": "clean_product"},
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )

    assert invalid_template.status_code == 400
    assert foreign_asset.status_code == 404


@pytest.mark.asyncio
async def test_provider_submission_failure_marks_task_failed(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    asset = await _seed_asset(db_session, tmp_path, monkeypatch)
    user = await _professional_user(db_session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    async def fake_submit(**kwargs):
        raise ValueError("供应商拒绝任务")

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_minimax_video",
        fake_submit,
    )
    response = await client.post(
        "/api/v1/videos/generate",
        json={
            "source_asset_id": str(asset.id),
            "prompt": "slow camera push in",
            "template_id": "clean_product",
            "model": "MiniMax-H3-Lite",
            "resolution": "480P",
            "duration": 4,
            "ratio": "9:16",
        },
        headers=auth_headers,
    )

    assert response.status_code == 502
    task = (
        await db_session.execute(
            select(VideoGenerationTask).where(VideoGenerationTask.user_id == user.id)
        )
    ).scalar_one()
    assert task.status == "failed"
    await db_session.refresh(user)
    assert user.credits == 200


@pytest.mark.asyncio
async def test_video_task_user_isolation_and_capabilities(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    task = VideoGenerationTask(
        user_id=(
            await db_session.execute(select(User.id).where(User.email == "test@example.com"))
        ).scalar_one(),
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        status="running",
    )
    db_session.add(task)
    await db_session.flush()

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"video-other-{uuid.uuid4().hex[:6]}@example.com",
            "username": "video-other",
            "password": "testpass123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    response = await client.get(
        f"/api/v1/videos/tasks/{task.id}",
        headers=other_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_video_history_and_missing_file(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
):
    user = await _professional_user(db_session)
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        status="succeeded",
        storage_key="missing.mp4",
    )
    db_session.add(task)
    await db_session.flush()

    history = await client.get("/api/v1/videos/history", headers=auth_headers)
    missing = await client.get(
        f"/api/v1/videos/tasks/{task.id}/file",
        headers=auth_headers,
    )

    assert history.status_code == 200
    assert history.json()[0]["id"] == str(task.id)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_cancel_video_task_uses_provider_and_marks_canceled(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    user = await _professional_user(db_session)
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        provider_task_id="provider-cancel",
        status="running",
    )
    db_session.add(task)
    await db_session.flush()

    async def fake_cancel(provider_task_id):
        assert provider_task_id == "provider-cancel"
        return True

    monkeypatch.setattr(
        "app.services.video_task_executor.cancel_minimax_video",
        fake_cancel,
    )
    response = await client.post(
        f"/api/v1/videos/tasks/{task.id}/cancel",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    await db_session.refresh(task)
    assert task.cancel_requested is True


@pytest.mark.asyncio
async def test_cancel_rejects_finished_or_remote_finished_task(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    monkeypatch,
):
    user = await _professional_user(db_session)
    finished = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        status="succeeded",
    )
    running = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        provider_task_id="finished-remote",
        status="running",
    )
    db_session.add_all([finished, running])
    await db_session.flush()

    async def fake_cancel(provider_task_id):
        return False

    monkeypatch.setattr(
        "app.services.video_task_executor.cancel_minimax_video",
        fake_cancel,
    )
    already_finished = await client.post(
        f"/api/v1/videos/tasks/{finished.id}/cancel",
        headers=auth_headers,
    )
    remote_finished = await client.post(
        f"/api/v1/videos/tasks/{running.id}/cancel",
        headers=auth_headers,
    )

    assert already_finished.status_code == 409
    assert remote_finished.status_code == 409


@pytest.mark.asyncio
async def test_video_file_requires_task_owner(
    client: AsyncClient,
    auth_headers: dict,
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _professional_user(db_session)
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        status="succeeded",
        storage_key=f"{user.id}/{uuid.uuid4()}.mp4",
    )
    path = tmp_path / task.storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42video")
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path))

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"video-file-{uuid.uuid4().hex[:6]}@example.com",
            "username": "video-file-other",
            "password": "testpass123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    denied = await client.get(
        f"/api/v1/videos/tasks/{task.id}/file",
        headers=other_headers,
    )
    allowed = await client.get(
        f"/api/v1/videos/tasks/{task.id}/file",
        headers=auth_headers,
    )

    assert denied.status_code == 404
    assert allowed.status_code == 200
    assert allowed.headers["content-type"].startswith("video/mp4")


@pytest.mark.asyncio
async def test_poll_video_task_pending_and_failure_states(
    db_session,
    auth_headers,
    monkeypatch,
):
    user = await _professional_user(db_session)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    queued = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="queued",
        provider_task_id="pending",
        status="running",
        next_poll_at=now,
    )
    failed = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="failed",
        provider_task_id="failed",
        status="running",
        next_poll_at=now,
    )
    db_session.add_all([queued, failed])
    await db_session.flush()

    async def fake_query(provider_task_id):
        if provider_task_id == "pending":
            return {"status": "queued"}
        return {"status": "failed", "error": "审核失败"}

    monkeypatch.setattr(
        "app.services.video_task_executor.query_minimax_video",
        fake_query,
    )

    count = await poll_video_tasks(db_session)
    await db_session.refresh(queued)
    await db_session.refresh(failed)

    assert count == 2
    assert queued.status == "running"
    assert queued.next_poll_at is not None
    assert failed.status == "failed"
    assert failed.error == "审核失败"


@pytest.mark.asyncio
async def test_poll_failure_limit_marks_task_failed(
    db_session,
    auth_headers,
    monkeypatch,
):
    user = await _professional_user(db_session)
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        provider_task_id="provider-error",
        status="running",
        poll_failures=4,
        next_poll_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db_session.add(task)
    await db_session.flush()

    async def fake_query(provider_task_id):
        raise ValueError("查询超时")

    monkeypatch.setattr(
        "app.services.video_task_executor.query_minimax_video",
        fake_query,
    )

    await poll_video_tasks(db_session)
    await db_session.refresh(task)

    assert task.status == "failed"
    assert task.poll_failures == 5
    assert "多次查询失败" in (task.error or "")


@pytest.mark.asyncio
async def test_poll_video_task_downloads_and_saves_mp4(
    db_session,
    tmp_path,
    monkeypatch,
    auth_headers,
):
    user = await _professional_user(db_session)
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=None,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="test",
        provider_task_id="provider-1",
        status="running",
        next_poll_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db_session.add(task)
    await db_session.flush()
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path))
    provider_config.clear_cache()

    async def fake_query(provider_task_id):
        return {
            "status": "succeeded",
            "video_url": "https://example.com/video.mp4",
            "duration": 4,
            "resolution": "480P",
            "ratio": "9:16",
        }

    async def fake_download(video_url):
        return b"\x00\x00\x00\x18ftypmp42" + b"video"

    monkeypatch.setattr(
        "app.services.video_task_executor.query_minimax_video",
        fake_query,
    )
    monkeypatch.setattr(
        "app.services.video_task_executor.download_minimax_video",
        fake_download,
    )

    count = await poll_video_tasks(db_session)
    await db_session.refresh(task)

    assert count == 1
    assert task.status == "succeeded"
    assert task.storage_key
    assert (tmp_path / task.storage_key).exists()
    assert (tmp_path / task.storage_key).read_bytes().startswith(b"\x00\x00\x00\x18ftyp")

