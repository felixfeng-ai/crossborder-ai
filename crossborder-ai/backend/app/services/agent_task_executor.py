"""VeyaShip - Agent 任务执行器

后台消费 agent_tasks 表：加载任务 → 重建用户/对话上下文 → 跑 Agent →
写回助手消息与自动标题 → 成功才扣积分 → 更新状态。

由 scheduler 的分发 job 调用，每个任务独立会话互不干扰；
执行失败只落 failed 状态、不向上抛异常，避免拖垮调度器。
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.agent_task import AgentTask
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import InsufficientCreditsError, User
from app.services.ai.agent_orchestrator import AgentOrchestrator

logger = logging.getLogger("veyaship")


async def execute_agent_task(task_id) -> None:
    """执行单个 Agent 任务。失败只更新任务状态为 failed，不抛异常。"""
    async with async_session_factory() as db:
        task = (await db.execute(
            select(AgentTask).where(AgentTask.id == task_id)
        )).scalar_one_or_none()
        if task is None or task.status != "running":
            # 已被调度器重新入队 / 已完成，跳过
            return

        user = (await db.execute(
            select(User).where(User.id == task.user_id)
        )).scalar_one_or_none()
        if user is None:
            task.status = "failed"
            task.error = "用户不存在"
            task.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return

        params = json.loads(task.input)
        now = datetime.now(timezone.utc)

        try:
            # 每完成一步 → 把累积 steps 写入任务 progress 列（SSE 端点轮询推流）。
            # 与编排器共用同一会话，commit 同时落中间产物（如已建商品），进程崩溃不丢。
            async def on_step(steps: list[dict]) -> None:
                task.progress = json.dumps({"steps": steps}, ensure_ascii=False)
                await db.commit()

            orchestrator = AgentOrchestrator(user, db, on_step=on_step)
            if task.task_type == "agent_workflow":
                result = await orchestrator.run_workflow(params["workflow"], params.get("params", {}))
                conv_id = None
            else:
                result = await orchestrator.run(params["instruction"])
                conv_id = UUID(params["conversation_id"]) if params.get("conversation_id") else None

            # 保存助手消息 + 自动生成对话标题（复用原同步逻辑）
            if conv_id is not None:
                conv = (await db.execute(
                    select(Conversation).where(Conversation.id == conv_id)
                )).scalar_one_or_none()
                if conv is not None:
                    instruction = params.get("instruction", "")
                    if not conv.title and instruction:
                        conv.title = instruction[:50] + ("..." if len(instruction) > 50 else "")
                    db.add(ConversationMessage(
                        conversation_id=conv_id,
                        role="assistant",
                        content=result.get("summary", ""),
                        steps=json.dumps(result.get("steps", []), ensure_ascii=False),
                    ))

            result_status = result.get("status", "success")
            if result_status in ("partial", "failed"):
                task.result = json.dumps({
                    "summary": result.get("summary", ""),
                    "steps": result.get("steps", []),
                    "status": result_status,
                    "conversation_id": str(conv_id) if conv_id else "",
                }, ensure_ascii=False)
                task.status = result_status
                task.error = result.get("summary", "") if result_status == "failed" else None
                task.finished_at = now
                await db.commit()
                logger.info("Agent 任务 %s 结束（%s），未扣积分", task.id, result_status)
                return

            # 成功才扣积分（幂等：每个任务只扣一次；行级锁防并发扣超）
            try:
                await user.deduct_credits(
                    db,
                    task.cost,
                    feature=task.task_type,
                    reference_type="agent_task",
                    reference_id=str(task.id),
                    description="AI Agent 任务执行",
                )
            except InsufficientCreditsError as e:
                task.status = "failed"
                task.error = str(e)
                task.finished_at = now
                await db.commit()
                return

            task.result = json.dumps({
                "summary": result.get("summary", ""),
                "steps": result.get("steps", []),
                "conversation_id": str(conv_id) if conv_id else "",
            }, ensure_ascii=False)
            task.status = "succeeded"
            task.finished_at = now
            await db.commit()
            logger.info("Agent 任务 %s 执行成功（%s）", task.id, task.task_type)
        except Exception as e:
            task.status = "failed"
            task.error = str(e)[:500]
            task.finished_at = now
            await db.commit()
            logger.warning("Agent 任务 %s 执行失败：%s", task.id, e)
