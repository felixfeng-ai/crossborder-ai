"""可审计的数据保留清理任务。"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent_task import AgentTask
from app.models.content import ContentGeneration, ContentStatus
from app.models.data_retention import DataRetentionRun
from app.models.image_generation_task import ImageGenerationTask
from app.models.store_check_log import StoreCheckLog


def _terminal_cleanup_targets() -> list[tuple[str, Any, tuple[Any, ...]]]:
    """返回可自动清理的临时记录，不包含仍被用户使用的商品和素材。"""
    return [
        (
            "image_generation_tasks",
            ImageGenerationTask,
            ("completed", "failed"),
        ),
        (
            "agent_tasks",
            AgentTask,
            ("succeeded", "failed"),
        ),
        (
            "content_generations",
            ContentGeneration,
            (ContentStatus.COMPLETED, ContentStatus.FAILED),
        ),
    ]


async def _delete_in_batches(
    db: AsyncSession,
    model: Any,
    statuses: tuple[Any, ...],
    cutoff: datetime,
    batch_size: int,
) -> int:
    """按主键批次删除终态记录。"""
    return await _delete_condition_in_batches(
        db,
        model,
        (
            model.created_at < cutoff,
            model.status.in_(statuses),
        ),
        batch_size,
    )


async def _delete_condition_in_batches(
    db: AsyncSession,
    model: Any,
    condition: tuple[Any, ...],
    batch_size: int,
) -> int:
    """小批次提交删除，避免大表一次删除长期持锁。"""
    deleted = 0
    id_column = model.id

    while True:
        id_result = await db.execute(
            select(id_column)
            .where(*condition)
            .limit(batch_size)
        )
        ids = id_result.scalars().all()
        if not ids:
            break

        result = await db.execute(delete(model).where(id_column.in_(ids)))
        removed = len(ids) if result.rowcount is None else max(result.rowcount, 0)
        if removed == 0:
            raise RuntimeError(f"{model.__tablename__} 批次删除未生效")
        deleted += removed
        await db.commit()

        if len(ids) < batch_size:
            break

    return deleted


async def run_retention_cleanup(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
    store_check_retention_days: int | None = None,
    dry_run: bool | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """执行一次数据保留清理并写入审计。

    dry_run 只统计候选数量。商品、Listing、素材库和用户主动对话不在此任务中删除，
    避免为了合规误删仍在使用的经营数据。
    """
    current_time = now or datetime.now(timezone.utc)
    keep_days = retention_days or settings.DATA_RETENTION_DAYS
    check_days = (
        store_check_retention_days or settings.DATA_RETENTION_STORE_CHECK_DAYS
    )
    simulate = settings.DATA_RETENTION_DRY_RUN if dry_run is None else dry_run
    batch = max(batch_size or settings.DATA_RETENTION_BATCH_SIZE, 1)
    cutoff = current_time - timedelta(days=keep_days)

    # 先提交审计起点，确保后续清理异常时仍能追溯本次执行。
    audit = DataRetentionRun(
        status="running",
        dry_run=simulate,
        retention_days=keep_days,
        store_check_retention_days=check_days,
        cutoff_at=cutoff,
        deleted_counts="{}",
    )
    db.add(audit)
    await db.commit()

    counts: dict[str, int] = {}
    try:
        for name, model, statuses in _terminal_cleanup_targets():
            condition = (
                model.created_at < cutoff,
                model.status.in_(statuses),
            )
            if simulate:
                counts[name] = int(
                    (
                        await db.execute(
                            select(func.count()).select_from(model).where(*condition)
                        )
                    ).scalar_one()
                    or 0
                )
            else:
                counts[name] = await _delete_in_batches(
                    db, model, statuses, cutoff, batch
                )

        store_check_cutoff = current_time - timedelta(days=check_days)
        store_check_condition = StoreCheckLog.created_at < store_check_cutoff
        if simulate:
            counts["store_check_logs"] = int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(StoreCheckLog)
                        .where(store_check_condition)
                    )
                ).scalar_one()
                or 0
            )
        else:
            counts["store_check_logs"] = await _delete_condition_in_batches(
                db,
                StoreCheckLog,
                (store_check_condition,),
                batch,
            )

        audit.status = "completed"
        audit.deleted_counts = json.dumps(counts, ensure_ascii=False)
        audit.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "run_id": str(audit.id),
            "dry_run": simulate,
            "cutoff_at": cutoff.isoformat(),
            "deleted": counts,
        }
    except Exception as exc:
        await db.rollback()
        failed = await db.get(DataRetentionRun, audit.id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)[:2000]
            failed.deleted_counts = json.dumps(counts, ensure_ascii=False)
            failed.finished_at = datetime.now(timezone.utc)
            await db.commit()
        raise
