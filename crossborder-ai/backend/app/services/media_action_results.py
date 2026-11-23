"""媒体任务终态回写 ActionRun 和工作项。"""

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_run import ActionRun
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.image_generation_task import ImageGenerationTask
from app.models.video_generation_task import VideoGenerationTask


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


async def sync_media_action_results(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> dict:
    """扫描已提交的媒体 ActionRun，把外部任务终态回写到用户工作项。"""

    runs = (
        await db.execute(
            select(ActionRun)
            .where(
                ActionRun.action_id.in_(
                    ["media.generate_image", "media.generate_video"]
                ),
                ActionRun.status == "verifying",
                ActionRun.external_id.is_not(None),
            )
            .order_by(ActionRun.created_at, ActionRun.id)
            .limit(max(1, limit))
        )
    ).scalars().all()
    completed = 0
    failed = 0
    waiting = 0
    now = datetime.now(timezone.utc)
    for run in runs:
        try:
            task_id = UUID(str(run.external_id))
        except (TypeError, ValueError):
            continue
        is_image = run.action_id == "media.generate_image"
        task = await db.get(
            ImageGenerationTask if is_image else VideoGenerationTask,
            task_id,
        )
        if task is None:
            waiting += 1
            continue
        status = str(task.status)
        if status in {"pending", "processing", "queued", "running"}:
            waiting += 1
            continue
        item = await db.get(WorkItem, run.work_item_id)
        if item is None:
            continue
        if status in {"completed", "succeeded"}:
            run.status = "succeeded"
            run.finished_at = now
            run.after_snapshot_json = _json(
                {
                    "task_id": str(task.id),
                    "status": status,
                    "image_urls": (
                        getattr(task, "image_urls", None) if is_image else None
                    ),
                    "storage_key": (
                        getattr(task, "storage_key", None)
                        if not is_image
                        else None
                    ),
                }
            )
            item.status = "succeeded"
            item.requires_action = "none"
            item.current_step = "媒体已生成"
            item.result_json = _json(
                {
                    "summary": "图片已生成" if is_image else "视频已生成",
                    "task_id": str(task.id),
                    "media_type": "image" if is_image else "video",
                }
            )
            event_type = "action_run.media_completed"
            completed += 1
        elif status in {"failed", "canceled"}:
            run.status = "cancelled" if status == "canceled" else "retryable_failed"
            run.error_code = "media_task_cancelled" if status == "canceled" else "media_task_failed"
            run.finished_at = now
            run.after_snapshot_json = _json(
                {"task_id": str(task.id), "status": status}
            )
            item.status = "waiting_user"
            item.requires_action = "retry"
            item.current_step = "媒体任务失败，可重试"
            item.result_json = _json(
                {
                    "summary": getattr(task, "error", None)
                    or "媒体任务未完成",
                    "task_id": str(task.id),
                }
            )
            event_type = "action_run.media_failed"
            failed += 1
        else:
            waiting += 1
            continue
        item.version += 1
        run.version += 1
        db.add(
            WorkItemEvent(
                workspace_id=item.workspace_id,
                work_item_id=item.id,
                event_type=event_type,
                payload_json=_json(
                    {
                        "action_run_id": str(run.id),
                        "task_id": str(task.id),
                        "status": status,
                    }
                ),
            )
        )
    await db.flush()
    return {
        "checked": len(runs),
        "completed": completed,
        "failed": failed,
        "waiting": waiting,
    }
