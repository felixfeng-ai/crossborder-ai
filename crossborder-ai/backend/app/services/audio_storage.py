"""语音对象存储接口。

默认使用本地私有目录；生产可切换到 S3 兼容对象存储。
业务层只传对象键，不直接依赖 boto3 或文件系统。
"""

import asyncio
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings


class AudioObjectStorage(Protocol):
    async def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def get_bytes(self, key: str) -> bytes: ...


class LocalObjectStorage:
    """语料目录内的本地私有对象存储。"""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _target(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("语音素材路径非法")
        return target

    def _put_sync(self, key: str, data: bytes) -> None:
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _delete_sync(self, key: str) -> None:
        self._target(key).unlink(missing_ok=True)

    async def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None:
        del content_type
        await asyncio.to_thread(self._put_sync, key, data)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    def _get_sync(self, key: str) -> bytes:
        return self._target(key).read_bytes()

    async def get_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, key)


class S3ObjectStorage:
    """S3 兼容私有 Bucket，默认启用服务端加密。"""

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        server_side_encryption: str = "AES256",
    ):
        self.client = client
        self.bucket = bucket
        self.server_side_encryption = server_side_encryption

    def _put_sync(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        payload: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if self.server_side_encryption:
            payload["ServerSideEncryption"] = self.server_side_encryption
        self.client.put_object(**payload)

    async def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None:
        await asyncio.to_thread(
            self._put_sync,
            key,
            data,
            content_type,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=self.bucket,
            Key=key,
        )

    def _get_sync(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    async def get_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, key)


def _build_s3_client() -> Any:
    """延迟导入 boto3，local 模式无需安装对象存储依赖。"""

    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "启用 S3 语音存储需要安装 boto3"
        ) from exc
    addressing_style = "path" if settings.S3_USE_PATH_STYLE else "virtual"
    return boto3.client(
        "s3",
        region_name=settings.S3_REGION or None,
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
        config=Config(s3={"addressing_style": addressing_style}),
    )


def get_audio_storage() -> AudioObjectStorage:
    backend = settings.AUDIO_STORAGE_BACKEND.strip().lower()
    if backend == "local":
        return LocalObjectStorage(settings.AUDIO_STORAGE_DIR)
    if backend == "s3":
        if not settings.S3_BUCKET.strip():
            raise RuntimeError("S3 语音存储缺少 S3_BUCKET")
        return S3ObjectStorage(
            client=_build_s3_client(),
            bucket=settings.S3_BUCKET.strip(),
            server_side_encryption=settings.S3_SERVER_SIDE_ENCRYPTION,
        )
    raise RuntimeError(f"不支持的语音存储后端：{backend}")
