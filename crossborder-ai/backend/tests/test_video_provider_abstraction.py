"""视频 Provider Registry 与 MiniMax 适配器。"""

import json
import uuid

import pytest

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services.video_provider import (
    MiniMaxVideoProvider,
    VideoImagePayload,
    VideoProviderRequest,
    get_video_provider,
    list_video_providers,
    register_video_provider,
)
from app.services.video_task_executor import submit_video_task


class FakeVideoProvider:
    name = "fake"

    def capabilities(self):
        return {"durations": [4], "supports_reference_images": True}

    async def submit(self, request):
        return "fake-task-1"

    async def query(self, provider_task_id):
        return {"status": "succeeded", "video_url": "https://example.com/fake.mp4"}

    async def cancel(self, provider_task_id):
        return True

    async def download(self, video_url):
        return b"fake-video"


def test_provider_registry_resolves_registered_provider():
    provider = FakeVideoProvider()
    register_video_provider(provider)

    assert get_video_provider("fake") is provider
    assert "fake" in list_video_providers()


def test_provider_registry_rejects_unknown_provider():
    with pytest.raises(ValueError, match="视频供应商"):
        get_video_provider("unknown-provider")


@pytest.mark.asyncio
async def test_minimax_adapter_normalizes_submit_and_lifecycle(monkeypatch):
    submitted = {}

    async def fake_submit(**kwargs):
        submitted.update(kwargs)
        return "minimax-task"

    async def fake_query(task_id):
        return {"status": "running"}

    async def fake_cancel(task_id):
        return True

    async def fake_download(url):
        return b"mp4"

    monkeypatch.setattr(
        "app.services.video_provider.submit_minimax_video",
        fake_submit,
    )
    monkeypatch.setattr(
        "app.services.video_provider.query_minimax_video",
        fake_query,
    )
    monkeypatch.setattr(
        "app.services.video_provider.cancel_minimax_video",
        fake_cancel,
    )
    monkeypatch.setattr(
        "app.services.video_provider.download_minimax_video",
        fake_download,
    )

    provider = MiniMaxVideoProvider()
    request = VideoProviderRequest(
        prompt="product shot",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        first_frame=VideoImagePayload(data=b"first", mime="image/png"),
        reference_images=[
            VideoImagePayload(data=b"ref", mime="image/webp"),
        ],
    )

    task_id = await provider.submit(request)
    queried = await provider.query(task_id)
    canceled = await provider.cancel(task_id)
    downloaded = await provider.download("https://example.com/video.mp4")

    assert task_id == "minimax-task"
    assert submitted["first_frame"] == b"first"
    assert submitted["reference_images"] == [(b"ref", "image/webp")]
    assert queried["status"] == "running"
    assert canceled is True
    assert downloaded == b"mp4"


@pytest.mark.asyncio
async def test_executor_submits_unified_request_through_registry(
    db_session,
    tmp_path,
    monkeypatch,
):
    class RecordingProvider:
        name = "recording"

        def __init__(self):
            self.request = None

        def capabilities(self):
            return {}

        async def submit(self, request):
            self.request = request
            return "recording-task"

        async def query(self, provider_task_id):
            return {}

        async def cancel(self, provider_task_id):
            return True

        async def download(self, video_url):
            return b""

    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user = User(
        id=uuid.uuid4(),
        email=f"provider-{uuid.uuid4().hex[:8]}@example.com",
        username="provider-user",
        password_hash="x",
        plan="professional",
        credits=100,
    )
    storage_key = f"{user.id}/source.png"
    source_path = tmp_path / storage_key
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"first-frame")
    asset = ImageAsset(
        user_id=user.id,
        name="Provider Test Product",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=320,
        height=320,
        file_size=len(b"first-frame"),
    )
    db_session.add_all([user, asset])
    await db_session.flush()
    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=asset.id,
        provider="recording",
        model="custom-model",
        resolution="720P",
        duration=5,
        ratio="9:16",
        prompt="premium product shot",
        status="queued",
    )
    db_session.add(task)
    await db_session.flush()

    provider = RecordingProvider()
    register_video_provider(provider)

    provider_task_id = await submit_video_task(db_session, task)

    assert provider_task_id == "recording-task"
    assert provider.request is not None
    assert provider.request.prompt == "premium product shot"
    assert provider.request.model == "custom-model"
    assert provider.request.duration == 5
    assert provider.request.first_frame == VideoImagePayload(
        data=b"first-frame",
        mime="image/png",
    )
    assert provider.request.reference_images == []
    assert task.provider_task_id == "recording-task"
    assert task.status == "running"


@pytest.mark.asyncio
async def test_executor_maps_multiple_product_references_to_provider(
    db_session,
    tmp_path,
    monkeypatch,
):
    class ReferenceProvider:
        name = "reference-provider"

        def __init__(self):
            self.request = None

        def capabilities(self):
            return {}

        async def submit(self, request):
            self.request = request
            return "reference-task"

        async def query(self, provider_task_id):
            return {}

        async def cancel(self, provider_task_id):
            return True

        async def download(self, video_url):
            return b""

    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    user = User(
        id=uuid.uuid4(),
        email=f"references-{uuid.uuid4().hex[:8]}@example.com",
        username="reference-user",
        password_hash="x",
        plan="professional",
        credits=100,
    )
    db_session.add(user)
    await db_session.flush()

    assets = []
    for index, content in enumerate((b"front", b"detail")):
        storage_key = f"{user.id}/reference-{index}.png"
        path = tmp_path / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        asset = ImageAsset(
            user_id=user.id,
            name=f"Reference {index}",
            kind="upload",
            storage_key=storage_key,
            content_type="image/png",
            width=320,
            height=320,
            file_size=len(content),
        )
        assets.append(asset)
    db_session.add_all(assets)
    await db_session.flush()

    task = VideoGenerationTask(
        user_id=user.id,
        source_asset_id=assets[0].id,
        reference_assets_json=json.dumps(
            [{"asset_id": str(asset.id), "role": "detail"} for asset in assets]
        ),
        provider="reference-provider",
        model="custom-model",
        resolution="720P",
        duration=5,
        ratio="9:16",
        prompt="multi-reference product shot",
        status="queued",
    )
    db_session.add(task)
    await db_session.flush()

    provider = ReferenceProvider()
    register_video_provider(provider)

    await submit_video_task(db_session, task)

    assert provider.request is not None
    assert provider.request.first_frame is None
    assert provider.request.reference_images == [
        VideoImagePayload(data=b"front", mime="image/png"),
        VideoImagePayload(data=b"detail", mime="image/png"),
    ]
