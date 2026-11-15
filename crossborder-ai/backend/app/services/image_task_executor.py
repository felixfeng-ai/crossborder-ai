"""图片生成持久任务执行器。"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services import provider_config  # 保留兼容入口，供运行时配置与旧测试替换。
from app.services.generated_image_assets import materialize_image_task_assets
from app.services.image_provider import (
    ImageProviderRequest,
    ImageReferencePayload,
    get_image_provider,
)
from app.services.image_quality import IMAGE_QUALITY_TIERS


logger = logging.getLogger("veyaship")


async def run_image_generation(
    db: AsyncSession,
    task_id: str | UUID,
    prompt: str,
    num_outputs: int,
) -> None:
    """执行图片生成并把状态、结果和失败原因写回数据库。"""
    try:
        tid = task_id if isinstance(task_id, UUID) else UUID(str(task_id))
    except (ValueError, TypeError):
        return

    existing = await db.get(ImageGenerationTask, tid)
    if existing is not None and existing.credits_charged > 0:
        return

    async def update(**fields) -> None:
        task = (
            await db.execute(
                select(ImageGenerationTask).where(ImageGenerationTask.id == tid)
            )
        ).scalar_one_or_none()
        if task is None:
            return
        for key, value in fields.items():
            setattr(task, key, value)
        await db.commit()

    try:
        # 调度器已完成抢占；这里再次标记 processing，兼容旧的直接调用入口。
        await update(status="processing")

        task = (
            await db.execute(
                select(ImageGenerationTask).where(ImageGenerationTask.id == tid)
            )
        ).scalar_one_or_none()
        if task is None:
            return

        references = await _load_task_references(db, task)
        request = _build_provider_request(
            task,
            prompt=prompt,
            num_outputs=num_outputs,
            references=references,
        )
        supported = [
            name
            for name in _provider_order(task)
            if get_image_provider(name).supports(task.mode, request.quality_tier)
        ]
        if not supported:
            await update(
                status="failed",
                error=(
                    "商品场景参考图生成服务暂不可用，请管理员检查 Replicate 配置"
                    if task.mode == "product_scene"
                    else "暂无可用图片生成服务，请稍后重试"
                ),
                finished_at=datetime.now(timezone.utc),
            )
            return

        errors: list[str] = []
        for provider_name in supported:
            try:
                provider = get_image_provider(provider_name)
                result = await provider.generate(request)
                if not result.urls:
                    raise ValueError("图片 Provider 未返回可用结果")
                await update(
                    status="completed",
                    image_urls=json.dumps(result.urls, ensure_ascii=False),
                    model_used=result.model,
                    provider=result.provider,
                    actual_cost_micros=result.actual_cost_micros,
                    error=None,
                    finished_at=datetime.now(timezone.utc),
                )
                try:
                    await materialize_image_task_assets(
                        db,
                        user_id=task.user_id,
                        task_id=tid,
                        prompt=prompt,
                        image_urls=result.urls,
                    )
                except Exception as exc:
                    # 生成成功优先；素材入库异常不能把任务改成失败。
                    logger.warning("生成图片自动入库异常 task=%s: %s", tid, exc)
                await _charge_completed_image_task(db, tid)
                return
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
                logger.warning("%s 图片生成失败: %s", provider_name, exc)
                # 商品场景和用户指定 Provider 不允许静默切到普通文生图。
                if task.mode == "product_scene" or task.provider != "auto":
                    break

        logger.warning("图片生成 Provider 全部失败 task=%s: %s", tid, errors)
        await update(
            status="failed",
            error=(
                "商品场景参考图生成失败，请稍后重试"
                if task.mode == "product_scene"
                else "图片生成失败，请稍后重试"
            ),
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.exception("图片生成任务执行异常: %s", exc)
        await update(
            status="failed",
            error="图片生成失败，请稍后重试",
            finished_at=datetime.now(timezone.utc),
        )


def _provider_order(task: ImageGenerationTask) -> list[str]:
    """商品场景只允许参考图 Provider；普通生成默认可在主备之间降级。"""
    if task.mode == "product_scene":
        return ["replicate"]
    if task.provider in {"aliyun", "replicate"}:
        return [task.provider]
    return ["aliyun", "replicate"]


def _build_provider_request(
    task: ImageGenerationTask,
    *,
    prompt: str,
    num_outputs: int,
    references: list[ImageReferencePayload],
) -> ImageProviderRequest:
    quality_tier = task.quality_tier or "fast"
    quality = IMAGE_QUALITY_TIERS.get(quality_tier)
    return ImageProviderRequest(
        prompt=prompt,
        mode=task.mode,
        quality_tier=quality_tier,
        resolution=task.resolution or (
            quality.resolution if quality is not None else "1024x1024"
        ),
        aspect_ratio=task.aspect_ratio or "1:1",
        num_outputs=max(1, min(int(num_outputs or 1), 4)),
        negative_prompt=task.negative_prompt or "",
        references=references,
    )


async def _load_task_references(
    db: AsyncSession,
    task: ImageGenerationTask,
) -> list[ImageReferencePayload]:
    """读取任务参考图并再次校验归属，避免历史脏数据串到别的用户。"""
    try:
        raw_ids = json.loads(task.reference_assets_json or "[]")
    except (TypeError, json.JSONDecodeError):
        raw_ids = []
    if not isinstance(raw_ids, list) or not raw_ids:
        return []

    parsed_ids = []
    for raw_id in raw_ids[:4]:
        try:
            parsed_ids.append(UUID(str(raw_id)))
        except (TypeError, ValueError):
            raise ValueError("参考素材 ID 无效")
    assets = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id.in_(parsed_ids),
                ImageAsset.user_id == task.user_id,
            )
        )
    ).scalars().all()
    if len(assets) != len(parsed_ids):
        raise ValueError("参考素材不存在或无权访问")

    base = Path(settings.IMAGE_STORAGE_DIR).resolve()
    by_id = {asset.id: asset for asset in assets}
    payloads = []
    for asset_id in parsed_ids:
        asset = by_id[asset_id]
        target = (base / asset.storage_key).resolve()
        if base not in target.parents and target != base:
            raise ValueError("参考素材路径无效")
        if not target.is_file():
            raise ValueError("参考素材文件不存在")
        if target.stat().st_size > settings.MAX_IMAGE_UPLOAD_BYTES:
            raise ValueError("参考素材超过大小限制")
        payloads.append(
            ImageReferencePayload(
                data=target.read_bytes(),
                mime=asset.content_type,
            )
        )
    return payloads


async def _charge_completed_image_task(db: AsyncSession, task_id: UUID) -> None:
    """图片生成成功后才扣积分，并通过 credits_charged 保证幂等。"""
    task = (
        await db.execute(
            select(ImageGenerationTask)
            .where(ImageGenerationTask.id == task_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        task is None
        or task.status != "completed"
        or task.credits_charged > 0
        or task.credits_cost <= 0
    ):
        return

    user = (
        await db.execute(
            select(User)
            .where(User.id == task.user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if user is None or user.credits < task.credits_cost:
        task.error = "图片已生成，但积分不足，请联系管理员"
        await db.commit()
        return

    await user.deduct_credits(
        db,
        task.credits_cost,
        feature="ai_image",
        reference_type="image_task",
        reference_id=str(task.id),
        description=f"AI 图片生成 {task.num_outputs} 张",
    )
    task.credits_charged = task.credits_cost
    await db.commit()


async def execute_image_generation_task(task_id: UUID) -> None:
    """执行调度器已抢占为 processing 的单条图片任务。"""
    async with async_session_factory() as db:
        task = (
            await db.execute(
                select(ImageGenerationTask).where(ImageGenerationTask.id == task_id)
            )
        ).scalar_one_or_none()
        # 任务不存在或已被其他 worker 完成时直接退出，保证重复调度安全。
        if task is None or task.status != "processing":
            return
        await run_image_generation(
            db,
            task.id,
            task.prompt,
            task.num_outputs,
        )
