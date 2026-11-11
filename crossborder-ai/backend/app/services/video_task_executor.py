"""MiniMax 视频任务执行器。

提交阶段只负责把用户首帧交给供应商并持久化远端任务 ID；
轮询阶段负责对账、下载成片并落入本地视频素材目录。
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services.credit_service import add_credits
from app.services.minimax_video import (
    cancel_minimax_video,
    download_minimax_video,
    query_minimax_video,
    submit_minimax_video,
    video_sha256,
)


logger = logging.getLogger("veyaship")

_POLL_INTERVAL = timedelta(seconds=5)
_MAX_POLL_FAILURES = 5


def _storage_path(storage_key: str) -> Path:
    """解析视频文件路径，并阻止目录穿越。"""
    base = Path(settings.VIDEO_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if target != base and base not in target.parents:
        raise ValueError("视频文件路径非法")
    return target


def _image_path(storage_key: str) -> Path:
    """解析首帧路径，确保只访问图片素材目录。"""
    base = Path(settings.IMAGE_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if target != base and base not in target.parents:
        raise ValueError("首帧文件路径非法")
    return target


async def submit_video_task(
    db: AsyncSession,
    task: VideoGenerationTask,
) -> str:
    """提交视频任务；成功后回写 provider task id 与运行状态。"""
    if task.source_asset_id is None:
        raise ValueError("缺少商品首帧")

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == task.source_asset_id,
                ImageAsset.user_id == task.user_id,
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise ValueError("商品首帧不存在")

    path = _image_path(asset.storage_key)
    if not path.is_file():
        raise ValueError("商品首帧文件不存在")

    provider_task_id = await submit_minimax_video(
        prompt=task.prompt,
        model=task.model,
        resolution=task.resolution,
        duration=task.duration,
        ratio=task.ratio,
        first_frame=path.read_bytes(),
        first_frame_mime=asset.content_type,
    )
    now = datetime.now(timezone.utc)
    task.provider_task_id = provider_task_id
    task.provider_status = "queued"
    task.status = "running"
    task.attempts += 1
    task.started_at = now
    task.next_poll_at = now + _POLL_INTERVAL
    task.error = None
    await db.flush()
    return provider_task_id


async def _save_video(
    task: VideoGenerationTask,
    data: bytes,
) -> None:
    """先写临时文件再原子替换，避免读取到下载了一半的 MP4。"""
    storage_key = f"{task.user_id}/{task.id}.mp4"
    target = _storage_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".mp4.part")
    temporary.write_bytes(data)
    temporary.replace(target)

    task.storage_key = storage_key
    task.mime = "video/mp4"
    task.file_size = len(data)
    task.sha256 = video_sha256(data)


async def _poll_one(db: AsyncSession, task: VideoGenerationTask) -> bool:
    """对账单条任务；返回是否在本次轮询中到达终态。"""
    if not task.provider_task_id:
        task.status = "failed"
        task.error = "视频任务缺少供应商任务 ID"
        task.finished_at = datetime.now(timezone.utc)
        await _refund_video_task(db, task)
        return True

    try:
        result = await query_minimax_video(task.provider_task_id)
        status = result["status"]
        task.provider_status = status

        if status in {"queued", "running"}:
            task.next_poll_at = datetime.now(timezone.utc) + _POLL_INTERVAL
            return False

        if status == "failed":
            task.status = "failed"
            task.error = result.get("error") or "视频生成失败"
            task.finished_at = datetime.now(timezone.utc)
            task.next_poll_at = None
            await _refund_video_task(db, task)
            return True

        if status == "canceled":
            task.status = "canceled"
            task.error = None
            task.finished_at = datetime.now(timezone.utc)
            task.next_poll_at = None
            await _refund_video_task(db, task)
            return True

        if status == "succeeded":
            video_url = result.get("video_url")
            if not video_url:
                raise ValueError("视频服务没有返回成片地址")
            data = await download_minimax_video(str(video_url))
            await _save_video(task, data)
            task.remote_video_url = str(video_url)
            task.status = "succeeded"
            task.error = None
            task.poll_failures = 0
            task.next_poll_at = None
            task.finished_at = datetime.now(timezone.utc)
            return True

        raise ValueError("视频任务状态无法识别")
    except Exception as exc:
        logger.warning("视频任务 %s 轮询失败：%s", task.id, exc)
        task.poll_failures += 1
        task.error = str(exc) or "视频任务查询失败"
        task.next_poll_at = datetime.now(timezone.utc) + _POLL_INTERVAL
        if task.poll_failures >= _MAX_POLL_FAILURES:
            task.status = "failed"
            task.error = "视频任务多次查询失败，请稍后重新生成"
            task.next_poll_at = None
            task.finished_at = datetime.now(timezone.utc)
            await _refund_video_task(db, task)
            return True
        return False


async def _refund_video_task(
    db: AsyncSession,
    task: VideoGenerationTask,
) -> int:
    """任务失败或取消时退回已扣积分，refunded 字段保证幂等。"""
    refundable = max(
        0,
        int(task.credits_charged or 0) - int(task.credits_refunded or 0),
    )
    if refundable <= 0:
        return 0
    user = (
        await db.execute(
            select(User).where(User.id == task.user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if user is None:
        return 0
    await add_credits(
        db,
        user,
        refundable,
        feature="ai_video_refund",
        reference_type="video_task",
        reference_id=str(task.id),
        description="视频生成失败自动退还积分",
    )
    task.credits_refunded += refundable
    await db.flush()
    return refundable


async def poll_video_tasks(db: AsyncSession, limit: int = 6) -> int:
    """轮询到期的运行中任务，返回本次处理数量。"""
    now = datetime.now(timezone.utc)
    tasks = (
        await db.execute(
            select(VideoGenerationTask)
            .where(
                VideoGenerationTask.status == "running",
                or_(
                    VideoGenerationTask.next_poll_at.is_(None),
                    VideoGenerationTask.next_poll_at <= now,
                ),
            )
            .order_by(VideoGenerationTask.next_poll_at, VideoGenerationTask.created_at)
            .limit(limit)
            .with_for_update()
        )
    ).scalars().all()

    processed = 0
    for task in tasks:
        await _poll_one(db, task)
        processed += 1

    if processed:
        await db.commit()
    return processed


async def cancel_video_task(
    db: AsyncSession,
    task: VideoGenerationTask,
) -> bool:
    """调用供应商取消接口，并把本地任务写入取消终态。"""
    try:
        remote_canceled = True
        if task.provider_task_id:
            remote_canceled = await cancel_minimax_video(task.provider_task_id)
        if not remote_canceled:
            return False

        task.status = "canceled"
        task.cancel_requested = True
        task.next_poll_at = None
        task.finished_at = datetime.now(timezone.utc)
        task.error = None
        await _refund_video_task(db, task)
        await db.flush()
        return True
    except Exception as exc:
        logger.warning("取消视频任务 %s 失败：%s", task.id, exc)
        task.error = str(exc) or "取消视频任务失败"
        await db.flush()
        return False
