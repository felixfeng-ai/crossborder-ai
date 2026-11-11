"""VeyaShip - Task Scheduler.

APScheduler-based periodic tasks for data synchronization,
credit management, and cleanup operations.
"""

import asyncio
import hashlib

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory, engine


class SchedulerService:
    """Manages periodic background tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def start(self):
        """Register and start all scheduled tasks."""
        # 每天清理过期临时记录；实际删除范围由 data_retention 服务统一控制。
        self.scheduler.add_job(
            self._cleanup_old_records_locked,
            CronTrigger(hour=3, minute=0),
            id="cleanup_old_records",
            replace_existing=True,
        )

        # Every 15 minutes: check for pending content generations
        self.scheduler.add_job(
            self._process_pending_generations,
            IntervalTrigger(minutes=15),
            id="process_pending_generations",
            replace_existing=True,
        )

        # Daily store check: 定时整店巡检
        self.scheduler.add_job(
            self._run_store_checks_locked,
            CronTrigger(hour=2, minute=30),  # 每天凌晨 2:30
            id="store_check_daily",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._run_operations_monitor_locked,
            CronTrigger(hour=2, minute=45),
            id="operations_monitor_daily",
            replace_existing=True,
        )

        # Every 5 seconds: 分发 Agent 异步任务（任务队列核心）
        # 在跨进程锁内抢占 pending 任务，锁外并发执行，多 worker 不重复消费
        self.scheduler.add_job(
            self._dispatch_agent_tasks,
            IntervalTrigger(seconds=5),
            id="dispatch_agent_tasks",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._dispatch_image_tasks,
            IntervalTrigger(seconds=5),
            id="dispatch_image_tasks",
            replace_existing=True,
        )

        # 每 10 秒对账一次 MiniMax 视频任务，跨进程锁避免多 worker 重复下载。
        self.scheduler.add_job(
            self._poll_video_tasks_locked,
            IntervalTrigger(seconds=10),
            id="poll_video_tasks",
            replace_existing=True,
        )

        # 镜头全部完成后合成营销成片；仍由跨进程锁保证单 worker 执行。
        self.scheduler.add_job(
            self._sync_marketing_videos_locked,
            IntervalTrigger(seconds=10),
            id="sync_marketing_videos",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._refresh_provider_cache,
            IntervalTrigger(seconds=10),
            id="refresh_provider_cache",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._refresh_monthly_credit_allowances_locked,
            CronTrigger(hour=3, minute=10),
            id="monthly_credit_allowance",
            replace_existing=True,
        )

        self.scheduler.start()
        print("[Scheduler] started with all jobs registered")

    async def _run_with_lock(self, lock_key: str, job):
        """在跨进程锁下执行 job，防止多 worker 重复执行。

        生产是 uvicorn 4 worker，每个 worker 各跑一份 APScheduler。
        不加锁时，凌晨 2:30 的整店巡检会在 4 个 worker 各写一份
        StoreCheckLog → 重复数据。用 PostgreSQL advisory lock 保证
        同一时刻只有一个 worker 真正执行 job。

        SQLite 开发模式单进程，无需锁，直接执行。
        """
        if settings.USE_SQLITE:
            return await job()

        # 确定性 64 位锁 key（md5 前 8 字节）。
        # 必须按「有符号 bigint」解析：advisory lock 用 PG int8（上限 2^63-1），
        # 无符号解析会有约一半 key 落在上界 → asyncpg 报 value out of int64 range。
        lock_id = int.from_bytes(hashlib.md5(lock_key.encode()).digest()[:8], "big", signed=True)
        # 独立连接持有锁，直到 job 结束才释放（session 级 advisory lock）
        async with engine.connect() as conn:
            got = (await conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_id}
            )).scalar()
            if not got:
                print(f"[Scheduler] 跳过 {lock_key}：其他 worker 正在执行")
                return None
            try:
                return await job()
            finally:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": lock_id}
                )

    async def _run_store_checks_locked(self):
        """带跨进程锁的定时整店巡检（防 4 worker 重复写巡检记录）。"""
        await self._run_with_lock("store_check_daily", self._run_store_checks)

    async def _run_operations_monitor_locked(self):
        """带跨进程锁的每日运营监控。"""
        await self._run_with_lock(
            "operations_monitor_daily",
            self._run_operations_monitor,
        )

    async def _run_operations_monitor(self):
        """扫描所有拥有 SKU 的用户并生成快照与预警。"""
        from app.services.operations_monitor import scan_all_users

        async with async_session_factory() as db:
            count = await scan_all_users(db)
            await db.commit()
            print(f"[Scheduler] 运营监控完成：{count} 个用户")

    async def _run_store_checks(self):
        """定时整店巡检：检查所有用户的商品，记录结果"""
        from app.models.product import Product
        from app.models.user import User
        from app.services.store_check_service import run_store_check

        async with async_session_factory() as db:
            # 找出有商品的用户
            result = await db.execute(
                select(Product.user_id).distinct()
            )
            user_ids = result.scalars().all()

            for user_id in user_ids:
                user = await db.get(User, user_id)
                if user is not None:
                    await run_store_check(db, user)

            await db.flush()
            await db.commit()
            print(f"[Scheduler] 定时巡检完成：{len(user_ids)} 个用户")

    async def stop(self):
        """Shut down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            print("[Scheduler] stopped")

    async def _cleanup_old_records_locked(self):
        """多 worker 下只允许一个实例执行数据保留清理。"""
        if not settings.DATA_RETENTION_ENABLED:
            return
        await self._run_with_lock("data_retention", self._cleanup_old_records)

    async def _cleanup_old_records(self):
        """删除过期临时记录，并写入 data_retention_runs 审计。"""
        from app.services.data_retention import run_retention_cleanup

        async with async_session_factory() as db:
            result = await run_retention_cleanup(db)
            print(
                "[Scheduler] 数据保留清理完成："
                f"dry_run={result['dry_run']} deleted={result['deleted']}"
            )

    async def _process_pending_generations(self):
        """Process any pending AI content generations."""
        # This would be replaced by a proper task queue (Celery/RQ)
        # for production use. For now, it's a placeholder.
        print("[Scheduler] No pending generations to process")

    # ── Agent 异步任务队列 ────────────────────────────────────────
    # 每 tick 每个 worker 最多抢占的任务数；4 worker 下并发上限约 4×4
    async def _dispatch_agent_tasks(self):
        """分发待执行的 Agent 任务：锁内抢占，锁外并发执行。"""
        claimed = await self._run_with_lock("dispatch_agent_tasks", self._claim_agent_tasks)
        if claimed:
            await asyncio.gather(*[self._execute_claimed_task(t) for t in claimed])

    async def _claim_agent_tasks(self):
        """在跨进程锁内抢占 pending 任务为 running，并恢复僵尸任务。

        锁只覆盖抢占这一步（毫秒级），真正的 Agent 执行在锁外并发跑，
        避免长任务占锁导致其他 worker 空等。

        顺序必须是「先抢 pending，再恢复僵尸」：若先恢复（status 置回
        pending）再抢，同一事务内 autoflush 会让刚恢复的僵尸任务在本
        tick 立即被抢回 running → 立即重跑，慢任务会被并发执行两次、
        扣两次积分。恢复的任务 commit 成 pending 后，下一 tick 才被抢占。
        """
        from app.models.agent_task import AgentTask

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)

            # 先抢占 pending（FOR UPDATE 行锁；advisory lock 已保证单 worker 抢占）
            result = await db.execute(
                select(AgentTask)
                .where(AgentTask.status == "pending")
                .order_by(AgentTask.created_at)
                .limit(4)
                .with_for_update()
            )
            claimed = result.scalars().all()
            for t in claimed:
                t.status = "running"
                t.started_at = now

            # 再恢复僵尸任务：worker 重启后任务会滞留 running。
            # running 超过 10 分钟 → 重新置回 pending（attempt+1），重试满 3 次 → failed。
            # 阈值取 10 分钟：慢任务（ReAct 多轮 DeepSeek 调用）通常 1-3 分钟，
            # 5 分钟易误判；真卡死的任务最多晚 10 分钟被重试。
            stale_result = await db.execute(
                select(AgentTask).where(
                    AgentTask.status == "running",
                    AgentTask.started_at < now - timedelta(minutes=10),
                )
            )
            for t in stale_result.scalars().all():
                if t.attempt >= 2:
                    t.status = "failed"
                    t.error = "执行超时，任务已终止，请重试"
                    t.finished_at = now
                else:
                    t.status = "pending"
                    t.attempt += 1
                    t.started_at = None

            await db.commit()
            return claimed

    async def _execute_claimed_task(self, task):
        """执行单个已抢占任务。异常只记日志，不拖垮调度器。"""
        from app.services.agent_task_executor import execute_agent_task

        try:
            await execute_agent_task(task.id)
        except Exception as e:
            print(f"[Scheduler] Agent 任务执行异常：{e}")

    # ── 图片持久化任务队列 ──────────────────────────────────────
    async def _dispatch_image_tasks(self):
        """抢占并分发图片任务。

        跨进程锁只覆盖数据库抢占阶段，真正的图片生成在锁外并发执行，
        避免慢请求长期占用 advisory lock。
        """
        claimed = await self._run_with_lock(
            "dispatch_image_tasks",
            self._claim_image_tasks,
        )
        if claimed:
            await asyncio.gather(
                *[self._execute_claimed_image_task(task.id) for task in claimed]
            )

    async def _claim_image_tasks(self):
        """抢占 pending 图片任务，并恢复进程崩溃后遗留的 processing 任务。"""
        from app.models.image_generation_task import ImageGenerationTask

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(ImageGenerationTask)
                .where(ImageGenerationTask.status == "pending")
                .order_by(ImageGenerationTask.created_at)
                .limit(4)
                .with_for_update()
            )
            claimed = result.scalars().all()
            for task in claimed:
                task.status = "processing"
                task.attempts += 1
                task.started_at = now

            # started_at 超过 10 分钟视为 worker 已失联；重试 3 次后终止。
            stale_result = await db.execute(
                select(ImageGenerationTask).where(
                    ImageGenerationTask.status == "processing",
                    ImageGenerationTask.started_at < now - timedelta(minutes=10),
                )
            )
            for task in stale_result.scalars().all():
                if task.attempts >= 3:
                    task.status = "failed"
                    task.error = "执行超时，任务已终止，请重试"
                    task.finished_at = now
                else:
                    task.status = "pending"
                    task.started_at = None

            await db.commit()
            return claimed

    async def _execute_claimed_image_task(self, task_id):
        from app.services.image_task_executor import execute_image_generation_task

        try:
            await execute_image_generation_task(task_id)
        except Exception as exc:
            print(f"[Scheduler] 图片任务执行异常：{exc}")

    async def _poll_video_tasks_locked(self):
        """对账运行中的视频任务，提交与下载都在锁内串行执行。"""
        await self._run_with_lock("poll_video_tasks", self._poll_video_tasks)

    async def _poll_video_tasks(self):
        from app.models.video_generation_task import VideoGenerationTask
        from app.services.video_task_executor import poll_video_tasks

        async with async_session_factory() as db:
            has_running = (
                await db.execute(
                    select(VideoGenerationTask.id)
                    .where(VideoGenerationTask.status == "running")
                    .limit(1)
                )
            ).scalar_one_or_none()
            if has_running is None:
                return
            count = await poll_video_tasks(db)
            print(f"[Scheduler] 视频任务对账完成：{count} 条")

    async def _sync_marketing_videos_locked(self):
        await self._run_with_lock(
            "sync_marketing_videos",
            self._sync_marketing_videos,
        )

    async def _sync_marketing_videos(self):
        from app.services.marketing_video_executor import (
            sync_marketing_video_projects,
        )

        async with async_session_factory() as db:
            count = await sync_marketing_video_projects(db)
            if count:
                print(f"[Scheduler] 营销视频项目对账完成：{count} 条")

    async def _refresh_provider_cache(self):
        """周期刷新服务商配置缓存，保证多 worker 在 10 秒内最终一致。"""
        from app.services import provider_config

        async with async_session_factory() as db:
            await provider_config.refresh(db)

    async def _refresh_monthly_credit_allowances_locked(self):
        """每日检查自然月额度，跨进程只允许一个 worker 发放。"""
        await self._run_with_lock(
            "monthly_credit_allowance",
            self._refresh_monthly_credit_allowances,
        )

    async def _refresh_monthly_credit_allowances(self):
        """给所有跨月用户补充额度；同月重复执行不会重复发放。"""
        from app.models.user import User
        from app.services.credit_service import apply_monthly_allowance

        async with async_session_factory() as db:
            users = (await db.execute(select(User))).scalars().all()
            applied = 0
            for user in users:
                transaction = await apply_monthly_allowance(db, user)
                if transaction is not None:
                    applied += 1
            await db.commit()
            print(f"[Scheduler] 月度积分额度检查完成：发放 {applied} 个账号")
