"""语音对象存储后端测试。"""

from pathlib import Path

import pytest

from app.core.config import settings
from app.services import audio_storage


@pytest.mark.asyncio
async def test_local_audio_storage_writes_and_deletes(tmp_path):
    storage = audio_storage.LocalObjectStorage(tmp_path)

    await storage.put_bytes(
        "private/audio/voice.m4a",
        b"audio-data",
        content_type="audio/mp4",
    )

    target = tmp_path / "private/audio/voice.m4a"
    assert target.read_bytes() == b"audio-data"
    await storage.delete("private/audio/voice.m4a")
    assert not target.exists()


@pytest.mark.asyncio
async def test_local_audio_storage_rejects_path_traversal(tmp_path):
    storage = audio_storage.LocalObjectStorage(tmp_path)

    with pytest.raises(ValueError, match="非法"):
        await storage.put_bytes(
            "../outside.m4a",
            b"audio-data",
            content_type="audio/mp4",
        )


@pytest.mark.asyncio
async def test_s3_audio_storage_uses_encryption_and_object_delete():
    class FakeS3:
        def __init__(self):
            self.put_calls = []
            self.delete_calls = []

        def put_object(self, **kwargs):
            self.put_calls.append(kwargs)

        def delete_object(self, **kwargs):
            self.delete_calls.append(kwargs)

    fake = FakeS3()
    storage = audio_storage.S3ObjectStorage(
        client=fake,
        bucket="veyaship-private",
        server_side_encryption="AES256",
    )

    await storage.put_bytes(
        "private/audio/voice.m4a",
        b"audio-data",
        content_type="audio/mp4",
    )
    await storage.delete("private/audio/voice.m4a")

    assert fake.put_calls == [
        {
            "Bucket": "veyaship-private",
            "Key": "private/audio/voice.m4a",
            "Body": b"audio-data",
            "ContentType": "audio/mp4",
            "ServerSideEncryption": "AES256",
        }
    ]
    assert fake.delete_calls == [
        {
            "Bucket": "veyaship-private",
            "Key": "private/audio/voice.m4a",
        }
    ]


def test_audio_storage_factory_selects_configured_backend(
    tmp_path,
    monkeypatch,
):
    fake = object()
    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "AUDIO_STORAGE_BACKEND", "local")
    local = audio_storage.get_audio_storage()
    assert isinstance(local, audio_storage.LocalObjectStorage)

    monkeypatch.setattr(settings, "AUDIO_STORAGE_BACKEND", "s3")
    monkeypatch.setattr(settings, "S3_BUCKET", "veyaship-private")
    monkeypatch.setattr(
        audio_storage,
        "_build_s3_client",
        lambda: fake,
    )
    remote = audio_storage.get_audio_storage()
    assert isinstance(remote, audio_storage.S3ObjectStorage)
