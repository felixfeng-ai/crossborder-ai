"""VeyaShip - Task Scheduler.

APScheduler-based periodic tasks for data synchronization,
credit management, and cleanup operations.
"""

import asyncio
import hashlib

from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        # 归档工作区保留期结束后独立清理，不混入临时数据保留任务。
        self.scheduler.add_job(
            self._purge_archived_workspaces_locked,
            CronTrigger(hour=3, minute=15),
            id="purge_archived_workspaces",
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

        # 每 6 小时同步启用 Shopify 店铺的订单和活动效果快照。
        self.scheduler.add_job(
            self._sync_all_shopify_operations_locked,
            IntervalTrigger(hours=6),
            id="shopify_operations_sync",
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

        # 每 5 秒把未处理的客服工作项写入 AgentTask，真正执行仍由上面的
        # Agent 任务队列统一抢占，避免值班 Worker 另造并发模型。
        self.scheduler.add_job(
            self._enqueue_customer_reply_tasks,
            IntervalTrigger(seconds=5),
            id="enqueue_customer_reply_tasks",
            replace_existing=True,
        )

        # 每 2 秒执行已确认且已接入适配器的受控领域动作。
        self.scheduler.add_job(
            self._dispatch_action_runs,
            IntervalTrigger(seconds=2),
            id="dispatch_action_runs",
            replace_existing=True,
        )

        # 每 5 分钟收取客服邮箱新增消息，Webhook 不可用时仍能补齐。
        self.scheduler.add_job(
            self._sync_customer_inboxes,
            IntervalTrigger(minutes=5),
            id="sync_customer_inboxes",
            replace_existing=True,
        )

        # 每小时按工作区本地时区生成晨报或日结。
        self.scheduler.add_job(
            self._run_daily_plans,
            CronTrigger(minute=0),
            id="daily_plan_schedule",
            replace_existing=True,
        )

        # 每 5 秒处理持久化通知待发，保证重启和多 worker 下仍可重试。
        self.scheduler.add_job(
            self._dispatch_notifications,
            IntervalTrigger(seconds=5),
            id="dispatch_notifications",
            replace_existing=True,
        )

        # 每 5 分钟增量同步订单信号，Webhook 丢失时由轮询补齐。
        self.scheduler.add_job(
            self._sync_shopify_order_signals,
            IntervalTrigger(minutes=5),
            id="shopify_order_signal_sync",
            replace_existing=True,
        )

        # Amazon Orders 限流很低，按 15 分钟单页监控 FBM 未发货订单。
        self.scheduler.add_job(
            self._sync_amazon_order_signals,
            IntervalTrigger(minutes=15),
            id="amazon_order_signal_sync",
            replace_existing=True,
        )

        # Temu LOCAL/SEMI 订单按 15 分钟巡检，只生成履约关注任务，不执行写操作。
        self.scheduler.add_job(
            self._sync_temu_order_signals,
            IntervalTrigger(minutes=15),
            id="temu_order_signal_sync",
            replace_existing=True,
        )

        # Temu V3 商品提交后按 15 分钟刷新原始平台状态。
        self.scheduler.add_job(
            self._sync_temu_listing_statuses,
            IntervalTrigger(minutes=15),
            id="temu_listing_status_sync",
            replace_existing=True,
        )

        # 每 10 分钟对账 Shopify 库存，只生成/关闭信号，不自动覆盖本地库存。
        self.scheduler.add_job(
            self._sync_shopify_inventory_signals,
            IntervalTrigger(minutes=10),
            id="shopify_inventory_signal_sync",
            replace_existing=True,
        )

        # 每 2 秒消费 Webhook 原始事件，请求线程只负责验签和落库。
        self.scheduler.add_job(
            self._process_integration_events,
            IntervalTrigger(seconds=2),
            id="process_integration_events",
            replace_existing=True,
        )

        # 每 10 秒把已完成的图片/视频任务回写到 ActionRun 和工作项。
        self.scheduler.add_job(
            self._sync_media_action_results,
            IntervalTrigger(seconds=10),
            id="sync_media_action_results",
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

        self.scheduler.add_job(
            self._expire_subscriptions_locked,
            CronTrigger(hour=2, minute=20),
            id="expire_user_subscriptions",
            replace_existing=True,
        )

        # 每 30 分钟对账个人用户账本与个人工作区镜像，默认只报告差异。
        self.scheduler.add_job(
            self._reconcile_workspace_billing_locked,
            IntervalTrigger(minutes=30),
            id="reconcile_workspace_billing",
            replace_existing=True,
        )

        # 月度额度检查完成后生成首个账期观察；默认关闭，切换后显式启用。
        self.scheduler.add_job(
            self._record_billing_observation_locked,
            CronTrigger(hour=3, minute=40),
            id="record_billing_observation_daily",
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

    async def _dispatch_action_runs(self):
        """在跨进程锁内分发动作，避免多个 Web 进程重复发布或退款。"""

        async def job():
            from app.services.action_dispatcher import (
                dispatch_queued_action_runs,
            )

            async with async_session_factory() as db:
                await dispatch_queued_action_runs(db, limit=5)

        await self._run_with_lock("dispatch_action_runs", job)

    async def _enqueue_customer_reply_tasks(self):
        """在跨进程锁内把客服工作项幂等写入 AgentTask 队列。"""

        async def job():
            from app.services.customer_reply_worker import (
                enqueue_customer_reply_tasks,
            )

            async with async_session_factory() as db:
                await enqueue_customer_reply_tasks(db)
                await db.commit()

        await self._run_with_lock("enqueue_customer_reply_tasks", job)

    async def _sync_customer_inboxes(self):
        """在跨进程锁内同步客服邮箱，避免重复创建工作项。"""

        async def job():
            from app.services.email_channel_service import (
                sync_all_customer_inboxes,
            )

            async with async_session_factory() as db:
                await sync_all_customer_inboxes(db)

        await self._run_with_lock("sync_customer_inboxes", job)

    async def _run_daily_plans(self):
        """按每小时本地时间触发各工作区的晨报与日结。"""

        async def job():
            from app.services.daily_plan import run_scheduled_daily_plans

            async with async_session_factory() as db:
                await run_scheduled_daily_plans(db)

        await self._run_with_lock("daily_plan_schedule", job)

    async def _dispatch_notifications(self):
        """在跨进程锁内发送通知，避免同一待发记录重复推送。"""

        async def job():
            from app.services.notifications import (
                dispatch_notification_outbox,
            )

            async with async_session_factory() as db:
                await dispatch_notification_outbox(db)
                await db.commit()

        await self._run_with_lock("dispatch_notifications", job)

    async def _sync_shopify_order_signals(self):
        """在跨进程锁内增量同步订单信号。"""

        async def job():
            from app.services.shopify_order_signal_sync import (
                sync_all_shopify_order_signals,
            )

            async with async_session_factory() as db:
                await sync_all_shopify_order_signals(db)

        await self._run_with_lock("shopify_order_signal_sync", job)

    async def _sync_amazon_order_signals(self):
        """在跨进程锁内同步 Amazon FBM 订单状态。"""

        async def job():
            from app.services.amazon_orders import (
                sync_all_amazon_order_signals,
            )

            async with async_session_factory() as db:
                await sync_all_amazon_order_signals(db)

        await self._run_with_lock("amazon_order_signal_sync", job)

    async def _sync_temu_order_signals(self):
        """在跨进程锁内巡检 Temu LOCAL/SEMI 履约风险。"""

        async def job():
            from app.services.temu_order_signal_sync import (
                sync_all_temu_order_signals,
            )

            async with async_session_factory() as db:
                await sync_all_temu_order_signals(db)

        await self._run_with_lock("temu_order_signal_sync", job)

    async def _sync_temu_listing_statuses(self):
        """在跨进程锁内刷新 Temu 商品原始发布状态。"""

        async def job():
            from app.services.temu_listing_status_sync import (
                sync_all_temu_listing_statuses,
            )

            async with async_session_factory() as db:
                await sync_all_temu_listing_statuses(db)
                await db.commit()

        await self._run_with_lock("temu_listing_status_sync", job)

    async def _sync_shopify_inventory_signals(self):
        """在跨进程锁内对账库存，冲突留给用户确认。"""

        async def job():
            from app.services.shopify_inventory_signal_sync import (
                sync_all_shopify_inventory_signals,
            )

            async with async_session_factory() as db:
                await sync_all_shopify_inventory_signals(db)

        await self._run_with_lock("shopify_inventory_signal_sync", job)

    async def _process_integration_events(self):
        """在跨进程锁内消费原始 Webhook 事件。"""

        async def job():
            from app.services.integration_events import (
                process_pending_integration_events,
            )

            async with async_session_factory() as db:
                await process_pending_integration_events(db)
                await db.commit()

        await self._run_with_lock("process_integration_events", job)

    async def _sync_media_action_results(self):
        """在跨进程锁内同步媒体动作终态。"""

        async def job():
            from app.services.media_action_results import (
                sync_media_action_results,
            )

            async with async_session_factory() as db:
                await sync_media_action_results(db)
                await db.commit()

        await self._run_with_lock("sync_media_action_results", job)

    async def _run_operations_monitor_locked(self):
        """带跨进程锁的每日运营监控。"""
        await self._run_with_lock(
            "operations_monitor_daily",
            self._run_operations_monitor,
        )

    async def _run_operations_monitor(self):
        """按用户开关扫描 SKU 并生成快照与预警。"""
        from app.services.automation_tasks import (
            run_scheduled_operations_monitors,
        )

        async with async_session_factory() as db:
            result = await run_scheduled_operations_monitors(db)
            await db.commit()
            print(
                "[Scheduler] 运营监控完成："
                f"{result['succeeded']} 成功，"
                f"{result['failed']} 失败，{result['skipped']} 跳过"
            )

    async def _sync_all_shopify_operations_locked(self):
        """多 worker 下只执行一份 Shopify 全局同步。"""
        await self._run_with_lock(
            "shopify_operations_sync",
            self._sync_all_shopify_operations,
        )

    async def _sync_all_shopify_operations(self):
        """自动同步所有启用 Shopify 店铺，并记录失败隔离结果。"""
        from app.services.shopify_operations_sync import (
            sync_all_shopify_operations,
        )

        async with async_session_factory() as db:
            result = await sync_all_shopify_operations(db, days=30)
            print(
                "[Scheduler] Shopify 自动同步完成："
                f"{result['channels_succeeded']}/{result['channels_scanned']} 成功，"
                f"{result['campaign_performance_updates']} 个活动更新"
            )

    async def _run_store_checks(self):
        """按用户开关执行定时整店巡检。"""
        from app.services.automation_tasks import run_scheduled_store_checks

        async with async_session_factory() as db:
            result = await run_scheduled_store_checks(db)
            await db.commit()
            print(
                "[Scheduler] 定时巡检完成："
                f"{result['succeeded']} 成功，"
                f"{result['failed']} 失败，{result['skipped']} 跳过"
            )

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

    async def _purge_archived_workspaces_locked(self):
        """归档工作区物理清理使用独立锁，避免多 Worker 重复删除。"""

        await self._run_with_lock(
            "purge_archived_workspaces",
            self._purge_archived_workspaces,
        )

    async def _purge_archived_workspaces(self):
        """清理保留期结束的归档工作区。"""

        from app.services.user_lifecycle import purge_expired_workspaces

        async with async_session_factory() as db:
            result = await purge_expired_workspaces(db)
            await db.commit()
            print(
                "[Scheduler] 归档工作区清理完成："
                f"{result['purged_count']} 个"
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
        """周期刷新服务商与访问控制缓存，保证多 worker 在 10 秒内最终一致。"""
        from app.core import access_control
        from app.services import provider_config

        async with async_session_factory() as db:
            await provider_config.refresh(db)
            await access_control.refresh(db)

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

    async def _expire_subscriptions_locked(self):
        """套餐到期处理：每日只允许一个 worker 执行。"""
        await self._run_with_lock(
            "expire_user_subscriptions",
            self._expire_subscriptions,
        )

    async def _expire_subscriptions(self):
        """过期订阅降级 Free，并保留购买积分。"""
        from app.services.plan_service import expire_due_subscriptions

        async with async_session_factory() as db:
            expired = await expire_due_subscriptions(db)
            await db.commit()
            print(f"[Scheduler] 套餐到期检查完成：降级 {expired} 个账号")

    async def _reconcile_workspace_billing_locked(self):
        """多 Worker 下只允许一个实例执行个人账务对账。"""
        await self._run_with_lock(
            "reconcile_workspace_billing",
            self._reconcile_workspace_billing,
        )

    async def _reconcile_workspace_billing(self):
        """对账个人钱包和订阅，不在定时任务中自动修改账务。"""
        from app.core.observability import emit_alert
        from app.services.workspace_billing_reconciliation import (
            reconcile_personal_workspace_billing,
        )

        async with async_session_factory() as db:
            result = await reconcile_personal_workspace_billing(
                db,
                record_cases=True,
            )
            # 案件记录是止付依据，必须在告警前持久化。
            await db.commit()
            ledger = result["ledger"]
            mismatch_count = (
                result["wallets"]["mismatched"]
                + result["subscriptions"]["mismatched"]
            )
            if mismatch_count or ledger["requires_attention"]:
                emit_alert(
                    "个人工作区账务对账发现差异",
                    context={
                        "wallet_mismatches": result["summary"][
                            "wallet_mismatches"
                        ],
                        "subscription_mismatches": result["summary"][
                            "subscription_mismatches"
                        ],
                        "workspace_count": result["summary"][
                            "workspace_count"
                        ],
                        "unassigned_transaction_count": ledger[
                            "unassigned_transaction_count"
                        ],
                        "unassigned_delta": ledger["unassigned_delta"],
                        "plan_credit_delta": ledger["plan_credit_delta"],
                        "purchased_credit_delta": ledger[
                            "purchased_credit_delta"
                        ],
                        "total_credit_delta": ledger["total_credit_delta"],
                    },
                )
            else:
                print(
                    "[Scheduler] 个人工作区账务对账完成：无差异"
                )

    async def _record_billing_observation_locked(self):
        """首个账期观察使用独立锁，避免多 Worker 重复写同一天文件。"""

        await self._run_with_lock(
            "record_billing_observation",
            self._record_billing_observation,
        )

    async def _record_billing_observation(self):
        """生成每日只读快照；失败必须告警并保留异常。"""

        if not settings.BILLING_OBSERVATION_ENABLED:
            print("[Scheduler] 首个账期观察未启用")
            return

        from app.core.observability import emit_alert
        from app.services.billing_observation import (
            collect_billing_observation,
            latest_observation_before,
            persist_billing_observation,
            read_observation_files,
        )

        directory = Path(settings.BILLING_OBSERVATION_DIR)
        observed_at = datetime.now(timezone.utc)
        since = observed_at.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        try:
            existing = read_observation_files(directory)
            async with async_session_factory() as db:
                observation = await collect_billing_observation(
                    db,
                    observed_at=observed_at,
                    since=since,
                    previous=latest_observation_before(
                        existing,
                        observed_at,
                    ),
                    allow_sqlite=settings.USE_SQLITE,
                    batch_size=settings.BILLING_OBSERVATION_BATCH_SIZE,
                )
            stored = persist_billing_observation(directory, observation)
            if observation["status"] != "passed":
                emit_alert(
                    "首个账期账务观察失败",
                    context={
                        "issues": observation["issues"],
                        "snapshot": observation["snapshot"],
                        "observation_file": str(stored["path"]),
                    },
                )
            else:
                print(
                    "[Scheduler] 首个账期观察通过："
                    f"连续 {stored['history']['consecutive_passed_days']} 天"
                )
        except Exception as exc:
            emit_alert(
                "首个账期账务观察执行失败",
                context={
                    "error": str(exc),
                    "observation_dir": str(directory),
                },
            )
            raise
