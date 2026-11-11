"""营销视频项目渲染与多镜头合成。"""

import hashlib
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.user import InsufficientCreditsError, User
from app.models.video_generation_task import VideoGenerationTask
from app.services.video_task_executor import cancel_video_task, submit_video_task


logger = logging.getLogger("veyaship")


def _ffmpeg_executable() -> str:
    """优先使用系统 FFmpeg，缺失时使用 Python 包内置二进制。"""
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        # 保留标准命令，让 subprocess 抛出清晰错误并由项目状态记录。
        return "ffmpeg"


def _video_path(storage_key: str) -> Path:
    base = Path(settings.VIDEO_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if target != base and base not in target.parents:
        raise ValueError("视频路径非法")
    return target


def _ffmpeg_concat_file(paths: list[Path], manifest: Path) -> None:
    """输出 concat demuxer 清单，并转义路径中的单引号。"""
    lines = []
    for path in paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def assemble_marketing_video(segment_paths: list[Path], output_path: Path) -> None:
    """使用 FFmpeg 按顺序拼接镜头；复制失败时回退到统一重编码。"""
    if not segment_paths:
        raise ValueError("没有可合成的视频镜头")
    missing = [str(path) for path in segment_paths if not path.is_file()]
    if missing:
        raise ValueError("有视频镜头文件不存在")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="veyaship-concat-",
        dir=str(output_path.parent),
        delete=False,
        encoding="utf-8",
    ) as handle:
        manifest = Path(handle.name)
    _ffmpeg_concat_file(segment_paths, manifest)

    copy_command = [
        _ffmpeg_executable(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        copied = subprocess.run(
            copy_command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if copied.returncode != 0 or not output_path.is_file():
            # 不同模型版本可能产生不同编码参数，统一重编码保证成片可播放。
            reencode_command = [
                _ffmpeg_executable(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            encoded = subprocess.run(
                reencode_command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if encoded.returncode != 0:
                raise ValueError("营销视频合成失败")
    finally:
        manifest.unlink(missing_ok=True)


async def start_marketing_project(
    db: AsyncSession,
    project: MarketingVideoProject,
    user: User,
) -> None:
    """提交项目中的全部分镜；全部受理后才扣除项目积分。"""
    if project.status != "brief_ready":
        raise ValueError("当前营销方案不能重复渲染")
    locked_user = (
        await db.execute(
            select(User).where(User.id == user.id).with_for_update()
        )
    ).scalar_one()
    if locked_user.credits < project.credits_estimated:
        raise InsufficientCreditsError(
            f"积分不足，本次营销视频需要 {project.credits_estimated} 积分"
        )

    shots = (
        await db.execute(
            select(MarketingVideoShot)
            .where(MarketingVideoShot.project_id == project.id)
            .order_by(MarketingVideoShot.position)
        )
    ).scalars().all()
    if not shots:
        raise ValueError("营销方案没有分镜")
    if not project.source_asset_id:
        raise ValueError("商品首帧已不存在")

    tasks: list[VideoGenerationTask] = []
    try:
        for shot in shots:
            task = VideoGenerationTask(
                user_id=project.user_id,
                source_asset_id=project.source_asset_id,
                template_id=project.template_id,
                provider="minimax",
                model=project.model,
                resolution=project.resolution,
                duration=shot.duration,
                ratio="9:16",
                prompt=shot.prompt,
                status="queued",
                credits_cost=0,
            )
            db.add(task)
            await db.flush()
            shot.video_task_id = task.id
            shot.status = "running"
            shot.error = None
            await submit_video_task(db, task)
            tasks.append(task)
    except Exception as exc:
        # 部分任务已被供应商受理时必须取消，避免项目失败后继续产生远端费用。
        for task in tasks:
            await cancel_video_task(db, task)
            task.status = "canceled"
        project.status = "failed"
        project.error = str(exc) or "营销视频提交失败"
        project.finished_at = datetime.now(timezone.utc)
        for shot in shots:
            shot.status = "failed" if shot.video_task_id is None else "canceled"
            shot.error = project.error
        await db.commit()
        raise ValueError(project.error)

    await locked_user.deduct_credits(db, project.credits_estimated)
    project.status = "rendering"
    project.credits_charged = project.credits_estimated
    project.approved_at = datetime.now(timezone.utc)
    project.error = None
    await db.flush()


def _file_sha256(path: Path) -> str:
    """分块计算成片哈希，避免把大文件一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


async def sync_marketing_video_projects(
    db: AsyncSession,
    limit: int = 4,
) -> int:
    """对账渲染中的项目，并在全部镜头完成后合成最终视频。"""
    projects = (
        await db.execute(
            select(MarketingVideoProject)
            .where(MarketingVideoProject.status == "rendering")
            .order_by(MarketingVideoProject.created_at)
            .limit(limit)
            .with_for_update()
        )
    ).scalars().all()

    processed = 0
    for project in projects:
        shots = (
            await db.execute(
                select(MarketingVideoShot)
                .where(MarketingVideoShot.project_id == project.id)
                .order_by(MarketingVideoShot.position)
            )
        ).scalars().all()
        task_ids = [shot.video_task_id for shot in shots if shot.video_task_id]
        tasks = (
            await db.execute(
                select(VideoGenerationTask).where(
                    VideoGenerationTask.id.in_(task_ids)
                )
            )
        ).scalars().all()
        task_by_id = {task.id: task for task in tasks}

        if not shots or len(task_by_id) != len(shots):
            project.status = "failed"
            project.error = "营销视频镜头任务不完整"
            project.finished_at = datetime.now(timezone.utc)
            processed += 1
            continue

        failed_task = next(
            (
                task_by_id[shot.video_task_id]
                for shot in shots
                if shot.video_task_id in task_by_id
                and task_by_id[shot.video_task_id].status
                in {"failed", "canceled"}
            ),
            None,
        )
        if failed_task is not None:
            project.status = "failed"
            project.error = failed_task.error or "营销视频有镜头生成失败"
            project.finished_at = datetime.now(timezone.utc)
            for shot in shots:
                task = task_by_id.get(shot.video_task_id)
                shot.status = task.status if task else "failed"
                shot.error = task.error if task else project.error
            processed += 1
            continue

        if any(
            task_by_id[shot.video_task_id].status != "succeeded"
            for shot in shots
        ):
            for shot in shots:
                shot.status = task_by_id[shot.video_task_id].status
            continue

        try:
            segment_paths = []
            for shot in shots:
                task = task_by_id[shot.video_task_id]
                if not task.storage_key:
                    raise ValueError("镜头视频文件缺失")
                segment_paths.append(_video_path(task.storage_key))

            relative_key = f"{project.user_id}/marketing-{project.id}.mp4"
            output_path = _video_path(relative_key)
            assemble_marketing_video(segment_paths, output_path)
            data_size = output_path.stat().st_size
            project.final_storage_key = relative_key
            project.mime = "video/mp4"
            project.file_size = data_size
            project.sha256 = _file_sha256(output_path)
            project.status = "succeeded"
            project.error = None
            project.finished_at = datetime.now(timezone.utc)
            for shot in shots:
                shot.status = "succeeded"
            processed += 1
        except Exception as exc:
            logger.warning("营销视频项目 %s 合成失败：%s", project.id, exc)
            project.status = "failed"
            project.error = str(exc) or "营销视频合成失败"
            project.finished_at = datetime.now(timezone.utc)
            processed += 1

    if processed:
        await db.commit()
    return processed


async def cancel_marketing_project(
    db: AsyncSession,
    project: MarketingVideoProject,
) -> bool:
    """取消仍在运行的镜头，并把项目写入取消终态。"""
    if project.status not in {"brief_ready", "rendering"}:
        return False
    if project.status == "brief_ready":
        project.status = "canceled"
        project.finished_at = datetime.now(timezone.utc)
        await db.flush()
        return True

    shots = (
        await db.execute(
            select(MarketingVideoShot).where(
                MarketingVideoShot.project_id == project.id
            )
        )
    ).scalars().all()
    tasks = (
        await db.execute(
            select(VideoGenerationTask).where(
                VideoGenerationTask.id.in_(
                    [shot.video_task_id for shot in shots if shot.video_task_id]
                )
            )
        )
    ).scalars().all()
    for task in tasks:
        if task.status == "running":
            await cancel_video_task(db, task)
    for shot in shots:
        if shot.status not in {"succeeded", "failed"}:
            shot.status = "canceled"
    project.status = "canceled"
    project.error = None
    project.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return True
