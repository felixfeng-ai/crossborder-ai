"""私有图片素材的显式公共 CDN/S3 发布。"""

import asyncio
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings
from app.models.image_asset import ImageAsset


IMAGE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class PublicImageStorage(Protocol):
    async def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> str: ...


class S3PublicImageStorage:
    """把公共图片写入 S3，并通过配置的 CDN 基地址返回 URL。"""

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        base_url: str,
        prefix: str = "public/images",
    ):
        if not base_url.startswith("https://"):
            raise ValueError("PUBLIC_MEDIA_BASE_URL 必须是 HTTPS 地址")
        self.client = client
        self.bucket = bucket
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix.strip("/")

    def _object_key(self, key: str) -> str:
        return "/".join(
            part for part in (self.prefix, key.strip("/")) if part
        )

    def _put_sync(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        object_key = self._object_key(key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{self.base_url}/{object_key}"

    async def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> str:
        return await asyncio.to_thread(
            self._put_sync,
            key,
            data,
            content_type,
        )


def _build_s3_client() -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("公共图片存储需要安装 boto3") from exc
    return boto3.client(
        "s3",
        region_name=settings.S3_REGION or None,
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
        config=Config(
            s3={
                "addressing_style": (
                    "path" if settings.S3_USE_PATH_STYLE else "virtual"
                )
            }
        ),
    )


def get_public_image_storage() -> PublicImageStorage:
    base_url = settings.PUBLIC_MEDIA_BASE_URL.strip()
    bucket = (
        settings.PUBLIC_MEDIA_S3_BUCKET.strip()
        or settings.S3_BUCKET.strip()
    )
    if not base_url or not bucket:
        raise RuntimeError(
            "公共图片托管尚未配置 PUBLIC_MEDIA_BASE_URL 和 S3 Bucket"
        )
    return S3PublicImageStorage(
        client=_build_s3_client(),
        bucket=bucket,
        base_url=base_url,
        prefix=settings.PUBLIC_MEDIA_PREFIX,
    )


async def publish_public_image_asset(
    asset: ImageAsset,
    *,
    storage: PublicImageStorage | None = None,
) -> str:
    """显式发布一张工作区图片，返回不可预测的持久公共 URL。"""

    if asset.deleted_at is not None:
        raise ValueError("已删除素材不能发布")
    if asset.workspace_id is None:
        raise ValueError("历史素材必须先绑定工作区")
    extension = IMAGE_EXTENSIONS.get(asset.content_type)
    if extension is None:
        raise ValueError("当前素材不是可发布的图片格式")
    base = Path(settings.IMAGE_STORAGE_DIR).resolve()
    target = (base / asset.storage_key).resolve()
    if base not in target.parents and target != base:
        raise ValueError("素材路径非法")
    if not target.is_file():
        raise ValueError("素材文件不存在")
    data = await asyncio.to_thread(target.read_bytes)
    key = (
        f"{asset.workspace_id}/{asset.id}.{extension}"
    )
    public_storage = storage or get_public_image_storage()
    return await public_storage.put_bytes(
        key,
        data,
        content_type=asset.content_type,
    )
