"""图片生成持久任务执行器。"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services import provider_config
from app.services.generated_image_assets import materialize_image_task_assets


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

        aliyun_key = provider_config.get(
            "aliyun",
            "api_key",
            settings.ALIYUN_DASHSCOPE_API_KEY or "",
        )
        # 主服务通义万相优先，失败后自动降级 Replicate。
        if aliyun_key:
            try:
                from app.services.ai.aliyun_image import AliyunImageService

                urls = await AliyunImageService().generate_image(
                    prompt=prompt,
                    num_outputs=num_outputs,
                )
                if urls:
                    await update(
                        status="completed",
                        image_urls=json.dumps(list(urls), ensure_ascii=False),
                        model_used=provider_config.get(
                            "aliyun",
                            "model",
                            settings.ALIYUN_IMAGE_MODEL,
                        ),
                        error=None,
                        finished_at=datetime.now(timezone.utc),
                    )
                    try:
                        await materialize_image_task_assets(
                            db,
                            user_id=existing.user_id,
                            task_id=tid,
                            prompt=prompt,
                            image_urls=list(urls),
                        )
                    except Exception as exc:
                        # 生成成功优先；素材入库异常不能把任务改成失败。
                        logger.warning("生成图片自动入库异常 task=%s: %s", tid, exc)
                    await _charge_completed_image_task(db, tid)
                    return
            except Exception as exc:
                logger.warning("Aliyun 图片生成失败，降级 Replicate: %s", exc)

        replicate_key = provider_config.get(
            "replicate",
            "api_key",
            settings.REPLICATE_API_KEY or "",
        )
        if replicate_key:
            try:
                from app.services.ai.replicate import ReplicateService

                urls = await ReplicateService().generate_image(
                    prompt=prompt,
                    num_outputs=num_outputs,
                )
                if urls:
                    await update(
                        status="completed",
                        image_urls=json.dumps(list(urls), ensure_ascii=False),
                        model_used=provider_config.get(
                            "replicate",
                            "model",
                            settings.REPLICATE_MODEL,
                        ),
                        error=None,
                        finished_at=datetime.now(timezone.utc),
                    )
                    try:
                        await materialize_image_task_assets(
                            db,
                            user_id=existing.user_id,
                            task_id=tid,
                            prompt=prompt,
                            image_urls=list(urls),
                        )
                    except Exception as exc:
                        logger.warning("生成图片自动入库异常 task=%s: %s", tid, exc)
                    await _charge_completed_image_task(db, tid)
                    return
            except Exception as exc:
                logger.warning("Replicate 图片生成失败: %s", exc)
                await update(
                    status="failed",
                    error="图片生成失败，请稍后重试",
                    finished_at=datetime.now(timezone.utc),
                )
                return

        await update(
            status="failed",
            error="暂无可用图片生成服务，请稍后重试",
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.exception("图片生成任务执行异常: %s", exc)
        await update(
            status="failed",
            error="图片生成失败，请稍后重试",
            finished_at=datetime.now(timezone.utc),
        )


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
