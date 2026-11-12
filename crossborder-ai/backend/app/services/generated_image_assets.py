"""把 AI 图片生成结果规范化为可复用图片素材。"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.services.image_processing import normalize_uploaded_image


logger = logging.getLogger("veyaship")


async def download_generated_image(url: str) -> bytes:
    """下载供应商结果并限制单图体积，避免异常响应占满存储。"""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.content
    if not data:
        raise ValueError("生成图片为空")
    if len(data) > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise ValueError("生成图片超过素材大小限制")
    return data


def _write_generated_asset(
    *,
    user_id: UUID,
    task_id: UUID,
    variant_index: int,
    data: bytes,
) -> tuple[str, int, int, int]:
    """在线程中完成图片校验、转码和落盘，避免阻塞事件循环。"""
    normalized, width, height = normalize_uploaded_image(
        data,
        settings.MAX_IMAGE_UPLOAD_BYTES,
    )
    storage_key = f"{user_id}/generated-{task_id}-{variant_index}.webp"
    base = Path(settings.IMAGE_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if base not in target.parents and target != base:
        raise ValueError("生成图片存储路径无效")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(normalized)
    return storage_key, width, height, len(normalized)


async def materialize_image_task_assets(
    db: AsyncSession,
    *,
    user_id: UUID,
    task_id: UUID,
    prompt: str,
    image_urls: list[str],
) -> list[ImageAsset]:
    """幂等保存生成结果；单张失败只跳过该变体。"""
    existing = (
        await db.execute(
            select(ImageAsset)
            .where(ImageAsset.generation_task_id == task_id)
            .order_by(ImageAsset.variant_index)
        )
    ).scalars().all()
    by_variant = {
        int(asset.variant_index): asset
        for asset in existing
        if asset.variant_index is not None
    }

    for variant_index, url in enumerate(image_urls[:4]):
        if variant_index in by_variant or not str(url).strip():
            continue
        try:
            data = await download_generated_image(str(url))
            storage_key, width, height, file_size = await asyncio.to_thread(
                _write_generated_asset,
                user_id=user_id,
                task_id=task_id,
                variant_index=variant_index,
                data=data,
            )
        except Exception as exc:
            logger.warning(
                "生成图片入库失败 task=%s variant=%s: %s",
                task_id,
                variant_index,
                exc,
            )
            continue

        asset = ImageAsset(
            user_id=user_id,
            name=f"AI 生成 · {prompt[:80]} · {variant_index + 1}"[:255],
            kind="generated",
            storage_key=storage_key,
            content_type="image/webp",
            width=width,
            height=height,
            file_size=file_size,
            generation_task_id=task_id,
            variant_index=variant_index,
        )
        db.add(asset)
        await db.flush()
        by_variant[variant_index] = asset

    return [by_variant[index] for index in sorted(by_variant)]
