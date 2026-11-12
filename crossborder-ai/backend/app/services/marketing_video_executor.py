"""营销视频项目渲染与多镜头合成。"""

import hashlib
import json
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
from app.services.credit_service import add_credits
from app.services.marketing_subtitles import build_marketing_srt
from app.services.professional_storyboard import provider_render_duration
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


def _subtitle_filter_path(path: Path) -> str:
    """转义 FFmpeg subtitles 滤镜路径，兼容 Windows 盘符。"""
    value = str(path.resolve()).replace("\\", "/")
    return value.replace(":", "\\:").replace("'", "\\'")


def trim_video_segment(source_path: Path, output_path: Path, duration: int) -> None:
    """把供应商生成视频精确裁切为脚本目标时长。"""
    if not source_path.is_file():
        raise ValueError("待裁切镜头文件不存在")
    if duration <= 0:
        raise ValueError("镜头裁切时长必须大于 0 秒")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg_executable(),
        "-y",
        "-i",
        str(source_path),
        "-t",
        str(int(duration)),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0 or not output_path.is_file():
        raise ValueError(f"镜头 {source_path.name} 裁切失败")


def assemble_marketing_video(
    segment_paths: list[Path],
    output_path: Path,
    subtitle_path: Path | None = None,
) -> bool:
    """拼接镜头并统一转为 H.264/AAC，确保浏览器可直接播放。

    供应商可能返回 H.265、混合帧率或不带音轨的 MP4。即使状态显示成功，
    浏览器也可能无法解码；因此最终成片不能依赖 ``-c copy``。
    """
    if not segment_paths:
        raise ValueError("没有可合成的视频镜头")
    missing = [str(path) for path in segment_paths if not path.is_file()]
    if missing:
        raise ValueError("有视频镜头文件不存在")
    if subtitle_path is not None and not subtitle_path.is_file():
        raise ValueError("营销视频字幕文件不存在")
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

    # 先写入独立的标准化文件，成功后再原子替换正式成片，避免失败时破坏旧文件。
    target_path = output_path.with_name(
        f"{output_path.stem}.standardized{output_path.suffix}"
    )
    normalize_command = [
        _ffmpeg_executable(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(target_path),
    ]
    burned_in = False
    try:
        normalized = subprocess.run(
            normalize_command,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if normalized.returncode != 0 or not target_path.is_file():
            raise ValueError("营销视频标准化失败")

        if subtitle_path is not None:
            subtitle_command = [
                _ffmpeg_executable(),
                "-y",
                "-i",
                str(target_path),
                "-vf",
                f"subtitles='{_subtitle_filter_path(subtitle_path)}'",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            subtitled = subprocess.run(
                subtitle_command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if subtitled.returncode == 0 and output_path.is_file():
                burned_in = True
            else:
                # 服务器可能没有 libass 或中文字体；独立 SRT 仍可下载。
                target_path.replace(output_path)
        else:
            target_path.replace(output_path)
    finally:
        manifest.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
    if not output_path.is_file():
        raise ValueError("营销视频合成失败")
    return burned_in


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
                duration=provider_render_duration(project.model, shot.duration),
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

    await locked_user.deduct_credits(
        db,
        project.credits_estimated,
        feature="marketing_video",
        reference_type="marketing_video_project",
        reference_id=str(project.id),
        description="营销成片渲染",
    )
    project.status = "rendering"
    project.credits_charged = project.credits_estimated
    project.approved_at = datetime.now(timezone.utc)
    project.error = None
    await db.flush()


async def _refund_marketing_project(
    db: AsyncSession,
    project: MarketingVideoProject,
) -> int:
    """项目失败或取消时退回整单积分，避免重复退款。"""
    refundable = max(
        0,
        int(project.credits_charged or 0) - int(project.credits_refunded or 0),
    )
    if refundable <= 0:
        return 0
    user = (
        await db.execute(
            select(User).where(User.id == project.user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if user is None:
        return 0
    await add_credits(
        db,
        user,
        refundable,
        feature="marketing_video_refund",
        reference_type="marketing_video_project",
        reference_id=str(project.id),
        description="营销成片失败自动退还积分",
    )
    project.credits_refunded += refundable
    await db.flush()
    return refundable


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
            await _refund_marketing_project(db, project)
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
            await _refund_marketing_project(db, project)
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

        temporary_segments: list[Path] = []
        subtitle_path: Path | None = None
        try:
            segment_paths = []
            for shot in shots:
                task = task_by_id[shot.video_task_id]
                if not task.storage_key:
                    raise ValueError("镜头视频文件缺失")
                segment_paths.append(_video_path(task.storage_key))

            relative_key = f"{project.user_id}/marketing-{project.id}.mp4"
            output_path = _video_path(relative_key)
            render_paths: list[Path] = []
            for shot, segment_path in zip(shots, segment_paths, strict=True):
                task = task_by_id[shot.video_task_id]
                if int(task.duration or 0) != int(shot.duration):
                    trimmed_path = output_path.with_name(
                        f"{output_path.stem}-shot-{shot.position}-trim.mp4"
                    )
                    trim_video_segment(segment_path, trimmed_path, shot.duration)
                    render_paths.append(trimmed_path)
                    temporary_segments.append(trimmed_path)
                else:
                    render_paths.append(segment_path)

            brief = json.loads(project.brief_json or "{}")
            shots_payload = [
                {
                    "position": shot.position,
                    "title": shot.title,
                    "duration": shot.duration,
                }
                for shot in shots
            ]
            if project.mode != "script" and not brief.get("no_subtitles"):
                subtitle_text = build_marketing_srt(brief, shots_payload)
                subtitle_path = output_path.with_name(
                    f"{output_path.stem}.subtitle{output_path.suffix}.srt"
                )
                subtitle_path.write_text(subtitle_text, encoding="utf-8")
            try:
                project.subtitles_burned_in = assemble_marketing_video(
                    render_paths,
                    output_path,
                    subtitle_path=subtitle_path,
                )
            finally:
                if subtitle_path is not None:
                    subtitle_path.unlink(missing_ok=True)
                for temporary_path in temporary_segments:
                    temporary_path.unlink(missing_ok=True)
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
            for temporary_path in temporary_segments:
                temporary_path.unlink(missing_ok=True)
            if subtitle_path is not None:
                subtitle_path.unlink(missing_ok=True)
            logger.warning("营销视频项目 %s 合成失败：%s", project.id, exc)
            project.status = "failed"
            project.error = str(exc) or "营销视频合成失败"
            project.finished_at = datetime.now(timezone.utc)
            await _refund_marketing_project(db, project)
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
    await _refund_marketing_project(db, project)
    await db.flush()
    return True
