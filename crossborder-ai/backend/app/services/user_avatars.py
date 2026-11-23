"""用户头像的校验、转码和私有文件存储。"""

import asyncio
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services.image_processing import normalize_uploaded_image


AVATAR_SIZE = 512


def normalize_avatar_image(data: bytes, *, max_bytes: int) -> bytes:
    """居中裁成方形并输出无元数据的 512px WebP。"""

    normalized, _, _ = normalize_uploaded_image(
        data,
        max_bytes,
        max_edge=2048,
    )
    try:
        with Image.open(io.BytesIO(normalized)) as source:
            has_alpha = source.mode in {"RGBA", "LA"} or (
                source.mode == "P" and "transparency" in source.info
            )
            image = source.convert("RGBA" if has_alpha else "RGB")
            side = min(image.size)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            square = image.crop((left, top, left + side, top + side))
            square = ImageOps.fit(
                square,
                (AVATAR_SIZE, AVATAR_SIZE),
                method=Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            square.save(output, format="WEBP", quality=88, method=4)
            return output.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("无法识别头像图片") from exc


def avatar_path(storage_key: str) -> Path:
    root = Path(settings.AVATAR_STORAGE_DIR).resolve()
    target = (root / storage_key).resolve()
    if target == root or root not in target.parents:
        raise ValueError("头像存储路径非法")
    return target


async def save_avatar_bytes(
    user_id: uuid.UUID,
    data: bytes,
) -> str:
    relative = f"{user_id}/{uuid.uuid4().hex}.webp"
    target = avatar_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_bytes, data)
    return relative


async def delete_avatar_file(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        target = avatar_path(storage_key)
    except ValueError:
        return
    await asyncio.to_thread(target.unlink, missing_ok=True)
