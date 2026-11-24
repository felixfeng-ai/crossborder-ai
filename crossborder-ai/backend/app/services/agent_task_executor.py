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

from sqlalchemy import or_, select

from app.core.database import async_session_factory
from app.models.agent_task import AgentTask
from app.models.agent_work import AgentTurn
from app.models.conversation import Conversation, ConversationMessage
from app.models.marketing_campaign import MarketingCampaign
from app.models.product import Product
from app.models.user import InsufficientCreditsError, User
from app.services.agent_context import (
    compact_conversation_history,
    extract_pending_action,
    is_confirmation,
)
from app.services.agent_turns import sync_agent_turn_status
from app.services.work_items import (
    complete_work_item_from_agent_task,
    create_work_items_from_agent_result,
)
from app.services.workspaces import ensure_personal_workspace
from app.services.ai.agent_orchestrator import AgentOrchestrator

logger = logging.getLogger("veyaship")


def build_campaign_context(campaign, product=None) -> str:
    """构造注入 Agent 的营销活动事实，避免模型自行猜测活动信息。"""
    try:
        brief = json.loads(campaign.brief_json or "{}")
    except (json.JSONDecodeError, TypeError):
        brief = {}
    lines = [
        f"活动名称：{campaign.title}",
        f"营销目标：{campaign.objective}",
        f"目标平台：{campaign.platform}",
        f"目标市场：{campaign.market}",
        f"内容语言：{campaign.language}",
        f"活动预算：{campaign.budget_credits} 积分",
        f"已消耗：{campaign.spent_credits} 积分",
    ]
    if isinstance(brief, dict) and brief:
        lines.append(f"活动补充信息：{json.dumps(brief, ensure_ascii=False)}")
    if product is not None:
        lines.extend([
            f"绑定商品：{product.title or product.url}",
            f"商品链接：{product.url}",
            f"参考供货价：{product.price if product.price is not None else '未知'}",
            f"品牌：{product.brand_name or '未设置'}",
            f"商品描述：{(product.description or '暂无')[:500]}",
        ])
    return "\n".join(lines)


def build_page_context(page_context: dict | None) -> str:
    """把侧栏传入的页面事实格式化后注入 Agent，不接收文件或页面正文。"""
    if not isinstance(page_context, dict):
        return ""

    lines: list[str] = []
    page = str(page_context.get("page") or "").strip()
    route = str(page_context.get("route") or "").strip()
    if page:
        lines.append(f"当前页面：{page}")
    if route:
        lines.append(f"页面路由：{route}")

    details = page_context.get("details")
    if isinstance(details, list):
        clean_details = [
            str(item).strip()
            for item in details[:6]
            if str(item).strip()
        ]
        if clean_details:
            lines.append(f"页面信息：{' | '.join(clean_details)}")

    for key, label in (
        ("product_id", "商品 ID"),
        ("asset_id", "素材 ID"),
        ("asset_name", "素材名称"),
        ("video_tab", "视频模式"),
        ("campaign_id", "活动 ID"),
    ):
        value = str(page_context.get(key) or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)


def _conversation_scope(
    workspace_id,
    *,
    allow_legacy_workspace: bool,
):
    """构造任务可访问的对话范围，显式工作区不得读取空归属历史。"""

    scope = Conversation.workspace_id == workspace_id
    if allow_legacy_workspace:
        scope = or_(scope, Conversation.workspace_id.is_(None))
    return scope


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
        if task.task_type == "customer_reply":
            from app.services.customer_reply_worker import (
                process_customer_reply_work_item,
            )

            try:
                result = await process_customer_reply_work_item(
                    db,
                    work_item_id=UUID(str(params["work_item_id"])),
                )
                task.result = json.dumps(result, ensure_ascii=False)
                task.status = "succeeded"
                task.finished_at = now
                await db.commit()
                logger.info(
                    "客服自动值班任务 %s 完成：%s",
                    task.id,
                    result.get("status"),
                )
            except Exception as exc:
                task.status = "failed"
                task.error = str(exc)[:500]
                task.finished_at = now
                await db.commit()
                logger.warning(
                    "客服自动值班任务 %s 失败：%s",
                    task.id,
                    exc,
                )
            return
        original_task_workspace_id = task.workspace_id
        workspace_id = original_task_workspace_id
        agent_turn = None
        page_context = params.get("page_context")
        if isinstance(page_context, dict) and page_context.get("agent_turn_id"):
            try:
                agent_turn = await db.get(
                    AgentTurn,
                    UUID(str(page_context["agent_turn_id"])),
                )
            except (TypeError, ValueError):
                agent_turn = None
            if agent_turn is not None:
                workspace_id = agent_turn.workspace_id
        if workspace_id is None:
            workspace_id = (await ensure_personal_workspace(db, user)).id

        try:
            if agent_turn is not None:
                await sync_agent_turn_status(
                    db,
                    turn=agent_turn,
                    task_status="running",
                )
                await db.commit()

            # 每完成一步 → 把累积 steps 写入任务 progress 列（SSE 端点轮询推流）。
            # 与编排器共用同一会话，commit 同时落中间产物（如已建商品），进程崩溃不丢。
            async def on_step(steps: list[dict]) -> None:
                task.progress = json.dumps({"steps": steps}, ensure_ascii=False)
                await db.commit()

            campaign = None
            product = None
            campaign_id = params.get("campaign_id")
            if task.task_type != "agent_workflow" and campaign_id:
                campaign = (
                    await db.execute(
                        select(MarketingCampaign).where(
                            MarketingCampaign.id == UUID(str(campaign_id)),
                            MarketingCampaign.user_id == task.user_id,
                            (
                                MarketingCampaign.workspace_id == workspace_id
                                if original_task_workspace_id is not None
                                else or_(
                                    MarketingCampaign.workspace_id
                                    == workspace_id,
                                    MarketingCampaign.workspace_id.is_(None),
                                )
                            ),
                        )
                    )
                ).scalar_one_or_none()
                if campaign is not None and campaign.product_id:
                    product = (
                        await db.execute(
                            select(Product).where(
                                Product.id == campaign.product_id,
                                Product.user_id == task.user_id,
                                (
                                    Product.workspace_id == workspace_id
                                    if original_task_workspace_id is not None
                                    else or_(
                                        Product.workspace_id == workspace_id,
                                        Product.workspace_id.is_(None),
                                    )
                                ),
                            )
                        )
                    ).scalar_one_or_none()

            orchestrator = AgentOrchestrator(
                user,
                db,
                on_step=on_step,
                campaign_id=str(campaign.id) if campaign is not None else None,
            )
            # 兼容测试和旧插件中的构造签名，同时让工具能按工作区校验 SKU。
            orchestrator.workspace_id = workspace_id
            if task.task_type == "agent_workflow":
                result = await orchestrator.run_workflow(params["workflow"], params.get("params", {}))
                conv_id = None
            else:
                instruction = params["instruction"]
                conv_id = (
                    UUID(params["conversation_id"])
                    if params.get("conversation_id")
                    else None
                )
                workspace = str(params.get("workspace") or "general")
                history_rows = []
                if conv_id is not None:
                    conv = (
                        await db.execute(
                            select(Conversation).where(
                                Conversation.id == conv_id,
                                Conversation.user_id == task.user_id,
                                _conversation_scope(
                                    workspace_id,
                                    allow_legacy_workspace=(
                                        original_task_workspace_id is None
                                    ),
                                ),
                            )
                        )
                    ).scalar_one_or_none()
                    if conv is not None:
                        workspace = conv.workspace or workspace
                    else:
                        conv_id = None
                if conv_id is not None:
                    history_rows = (
                        await db.execute(
                            select(ConversationMessage)
                            .where(ConversationMessage.conversation_id == conv_id)
                            .order_by(ConversationMessage.created_at.desc())
                            .limit(24)
                        )
                    ).scalars().all()
                    history_rows.reverse()
                orchestrator.workspace = workspace
                raw_history = [
                    {
                        "role": message.role,
                        "content": message.content,
                        "steps": message.steps,
                    }
                    for message in history_rows
                ]
                pending_action = extract_pending_action(raw_history)
                if campaign is not None:
                    instruction = (
                        f"{instruction}\n\n[营销活动上下文]\n"
                        f"{build_campaign_context(campaign, product)}"
                    )
                page_context_text = build_page_context(
                    params.get("page_context")
                )
                if page_context_text:
                    instruction = (
                        f"{instruction}\n\n[当前页面上下文]\n"
                        f"{page_context_text}"
                    )
                if pending_action is not None and is_confirmation(
                    params.get("instruction", "")
                ):
                    result = await orchestrator.run_confirmed_action(
                        pending_action.action,
                        pending_action.params,
                    )
                else:
                    result = await orchestrator.run(
                        instruction,
                        history=compact_conversation_history(
                            raw_history,
                            current_instruction=params.get("instruction", ""),
                        ),
                    )

            pending_items = await create_work_items_from_agent_result(
                db,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                agent_task_id=task.id,
                result=result,
            )
            result["created_work_item_ids"] = [
                str(item.id) for item in pending_items
            ]

            # 保存助手消息 + 自动生成对话标题（复用原同步逻辑）
            if conv_id is not None:
                conv = (await db.execute(
                    select(Conversation).where(
                        Conversation.id == conv_id,
                        Conversation.user_id == task.user_id,
                        _conversation_scope(
                            workspace_id,
                            allow_legacy_workspace=(
                                original_task_workspace_id is None
                            ),
                        ),
                    )
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
                    "created_work_item_ids": result.get("created_work_item_ids", []),
                }, ensure_ascii=False)
                task.status = result_status
                task.error = result.get("summary", "") if result_status == "failed" else None
                task.finished_at = now
                # 用户任务必须同步反映 Agent 失败，不能只更新内部任务表。
                await complete_work_item_from_agent_task(
                    db,
                    agent_task_id=task.id,
                    status="failed",
                    summary=result.get("summary", ""),
                    error=task.error,
                )
                if agent_turn is not None:
                    await sync_agent_turn_status(
                        db,
                        turn=agent_turn,
                        task_status=result_status,
                    )
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
                await complete_work_item_from_agent_task(
                    db,
                    agent_task_id=task.id,
                    status="failed",
                    summary="积分不足，任务未执行",
                    error=str(e),
                )
                if agent_turn is not None:
                    await sync_agent_turn_status(
                        db,
                        turn=agent_turn,
                        task_status="failed",
                    )
                await db.commit()
                return

            task.result = json.dumps({
                "summary": result.get("summary", ""),
                "steps": result.get("steps", []),
                "conversation_id": str(conv_id) if conv_id else "",
                "created_work_item_ids": result.get("created_work_item_ids", []),
            }, ensure_ascii=False)
            task.status = "succeeded"
            task.finished_at = now
            # 成功状态与用户可见结果同事务提交，避免 App 看到“已完成”但结果为空。
            await complete_work_item_from_agent_task(
                db,
                agent_task_id=task.id,
                status="succeeded",
                summary=result.get("summary", ""),
                error=None,
            )
            if agent_turn is not None:
                await sync_agent_turn_status(
                    db,
                    turn=agent_turn,
                    task_status="succeeded",
                )
            await db.commit()
            logger.info("Agent 任务 %s 执行成功（%s）", task.id, task.task_type)
        except Exception as e:
            task.status = "failed"
            task.error = str(e)[:500]
            task.finished_at = now
            await complete_work_item_from_agent_task(
                db,
                agent_task_id=task.id,
                status="failed",
                summary="Agent 执行失败",
                error=task.error,
            )
            if agent_turn is not None:
                await sync_agent_turn_status(
                    db,
                    turn=agent_turn,
                    task_status="failed",
                )
            await db.commit()
            logger.warning("Agent 任务 %s 执行失败：%s", task.id, e)
