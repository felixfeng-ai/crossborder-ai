"""VeyaShip AI - AI Agent 智能助手路由

支持持久化对话、上下文记忆、继续对话。
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.core.access_control import check_feature_access
from app.dependencies import get_current_user
from app.models.user import User
from app.models.conversation import Conversation, ConversationMessage
from app.models.agent_task import AgentTask
from app.models.marketing_campaign import MarketingCampaign
from pydantic import BaseModel, Field

router = APIRouter(prefix="/agent", tags=["AI 智能助手"])

# ════════════════════════════════════════════════════════════════
# 工作流模板（预设）
# ════════════════════════════════════════════════════════════════

# 预设工作流模板（单一数据源）：/workflows 展示与 /workflow 执行统一从这里读，
# 保证前端标注的积分与实际扣费一致（曾出现列表标 cost=1、执行硬编码 cost=2 的不一致）。
WORKFLOW_TEMPLATES: dict[str, dict] = {
    "select_products": {"id": "select_products", "name": "AI 选品决策", "desc": "输入品类 → AI 推荐值得做的商品 + 利润估算", "cost": 2},
    "decision_and_list": {"id": "decision_and_list", "name": "判断商品 + 生成 Listing", "desc": "分析能不能做 → 生成 Listing → 合规修复", "cost": 2},
    "store_check": {"id": "store_check", "name": "整店巡检", "desc": "检查所有商品状态，找出待处理问题", "cost": 1},
    "1688_to_shopify": {"id": "1688_to_shopify", "name": "1688 → Shopify 上架", "desc": "抓取商品 → AI 生成 Listing → 发布到 Shopify", "cost": 2},
    "1688_to_amazon": {"id": "1688_to_amazon", "name": "1688 → Amazon Listing", "desc": "抓取商品 → AI 生成 Amazon Listing 与合规结果", "cost": 2},
    "scrape_and_list": {"id": "scrape_and_list", "name": "抓取 + 生成 Listing", "desc": "抓取 1688 商品 → AI 生成 Listing", "cost": 1},
}

AGENT_WORKSPACES = {"general", "marketing"}


def _normalize_workspace(value: str) -> str:
    normalized = str(value or "general").strip().lower()
    return normalized if normalized in AGENT_WORKSPACES else "general"


@router.get("/workflows")
async def list_workflows():
    """列出预设工作流模板（含积分价，前端用于展示）"""
    return {"workflows": list(WORKFLOW_TEMPLATES.values())}

# ════════════════════════════════════════════════════════════════
# 对话管理
# ════════════════════════════════════════════════════════════════

@router.get("/conversations")
async def list_conversations(
    page: int = Query(1, ge=1),
    workspace: str = Query("general"),
    campaign_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用户的对话历史列表"""
    filters = [
        Conversation.user_id == current_user.id,
        Conversation.workspace == _normalize_workspace(workspace),
    ]
    if campaign_id is not None:
        if campaign_id:
            from uuid import UUID
            try:
                filters.append(Conversation.campaign_id == UUID(campaign_id))
            except ValueError:
                raise HTTPException(status_code=400, detail="无效的活动ID")
        else:
            filters.append(Conversation.campaign_id.is_(None))
    query = select(Conversation).where(*filters).order_by(desc(Conversation.updated_at))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    result = await db.execute(query.offset((page - 1) * 20).limit(20))
    convs = result.scalars().all()

    return {
        "items": [{"id": str(c.id), "title": c.title or "新对话", "created_at": str(c.created_at), "message_count": 0} for c in convs],
        "total": total or 0,
    }


@router.post("/conversations")
async def create_conversation(
    workspace: str = Query("general"),
    campaign_id: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新的对话会话"""
    parsed_campaign_id = None
    if campaign_id:
        from uuid import UUID
        try:
            parsed_campaign_id = UUID(campaign_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的活动ID")
        campaign = (
            await db.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.id == parsed_campaign_id,
                    MarketingCampaign.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=404, detail="营销活动不存在")
    conv = Conversation(
        user_id=current_user.id,
        workspace=_normalize_workspace(workspace),
        campaign_id=parsed_campaign_id,
    )
    db.add(conv)
    await db.flush()
    return {"id": str(conv.id), "title": "新对话"}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取对话的完整消息历史"""
    from uuid import UUID
    try:
        cid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的对话ID")

    conv = (await db.execute(select(Conversation).where(Conversation.id == cid, Conversation.user_id == current_user.id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    msgs = (await db.execute(
        select(ConversationMessage).where(ConversationMessage.conversation_id == cid).order_by(ConversationMessage.created_at)
    )).scalars().all()

    return {
        "id": str(conv.id),
        "title": conv.title or "新对话",
        "messages": [
            {"role": m.role, "content": m.content, "steps": json.loads(m.steps) if m.steps else None, "created_at": str(m.created_at)}
            for m in msgs
        ],
    }

# ════════════════════════════════════════════════════════════════
# Agent 执行（支持对话持久化）
# ════════════════════════════════════════════════════════════════

class AgentRequest(BaseModel):
    instruction: str = Field(..., min_length=2, max_length=2000)
    conversation_id: str = Field("", description="对话ID，留空创建新对话")
    workspace: str = Field("general", description="Agent 工作区")
    campaign_id: str = Field("", description="营销活动 ID")


def _task_response(task: AgentTask) -> dict:
    """把任务记录转成前端轮询用的响应结构。"""
    result = json.loads(task.result) if task.result else {}
    inp = json.loads(task.input) if task.input else {}
    return {
        "task_id": str(task.id),
        "status": task.status,
        "summary": result.get("summary", ""),
        "steps": result.get("steps", []),
        "conversation_id": result.get("conversation_id") or inp.get("conversation_id", ""),
        "error": task.error,
    }


# ════════════════════════════════════════════════════════════════
# 流式输出（SSE）：任务执行时实时推步骤进度，替代 2s 轮询
# ════════════════════════════════════════════════════════════════

# SSE 端点轮询 DB 的间隔（秒）。生产 4 worker 各跑一份调度器，
# 执行器与 SSE 连接可能落在不同进程 → 只能以 DB（progress 列）为共享事实源。
STREAM_POLL_INTERVAL = 1.0


def _sse_event(fresh: AgentTask, last_status: str | None, last_step_count: int) -> tuple[bool, str | None, int]:
    """根据任务最新状态计算要推送的 SSE 事件（纯函数，便于测试）。

    Args:
        fresh: 最新任务记录
        last_status: 上一次推送时的任务状态（None 表示首次）
        last_step_count: 上一次推送时已完成的步骤数

    Returns:
        (changed, event_text, step_count)：
        - changed=False 时 event_text 为 None（状态没变，无需推送）
        - 执行中推送 `event: step`（携带累计 steps）
        - 结束推送 `event: done`（succeeded 带 summary/steps / failed 带 error）
    """
    status = fresh.status
    steps: list = []
    if fresh.progress:
        try:
            steps = json.loads(fresh.progress).get("steps", []) or []
        except (json.JSONDecodeError, AttributeError, TypeError):
            steps = []

    changed = status != last_status or len(steps) != last_step_count
    if not changed:
        return False, None, len(steps)

    if status in ("succeeded", "partial", "failed"):
        if status == "succeeded":
            result = json.loads(fresh.result) if fresh.result else {}
            payload = {
                "status": "succeeded",
                "summary": result.get("summary", ""),
                "steps": result.get("steps") or steps,
                "conversation_id": result.get("conversation_id", ""),
            }
        elif status == "partial":
            result = json.loads(fresh.result) if fresh.result else {}
            payload = {
                "status": "partial",
                "summary": result.get("summary", ""),
                "steps": result.get("steps") or steps,
                "conversation_id": result.get("conversation_id", ""),
            }
        else:
            payload = {"status": "failed", "error": fresh.error or "任务执行失败，请重试"}
        return True, f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n", len(steps)

    payload = {"status": status, "steps": steps}
    return True, f"event: step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n", len(steps)


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_agent(
    payload: AgentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    """提交 AI Agent 执行任务（异步，立即返回 task_id，前端轮询结果）

    幂等：携带 Idempotency-Key 头时，同一 key 重复提交返回已有任务，
    不再重复建对话 / 重复扣积分。
    """
    from uuid import UUID

    cost = 1
    if not check_feature_access(current_user, "agent"):
        raise HTTPException(status_code=403, detail="AI 智能助手仅限 Standard 及以上套餐使用")

    campaign_id = ""
    campaign_uuid = None
    if payload.campaign_id:
        from uuid import UUID
        try:
            campaign_uuid = UUID(payload.campaign_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="营销活动不存在")
        campaign = (
            await db.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.id == campaign_uuid,
                    MarketingCampaign.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=404, detail="营销活动不存在")
        campaign_id = str(campaign.id)

    if current_user.credits < cost:
        raise HTTPException(status_code=402, detail="积分不足")

    # 幂等：同一 Idempotency-Key 重复提交 → 返回已有任务
    if idempotency_key:
        existing = (await db.execute(
            select(AgentTask).where(
                AgentTask.user_id == current_user.id,
                AgentTask.idempotency_key == idempotency_key,
            )
        )).scalar_one_or_none()
        if existing:
            return _task_response(existing)

    # 查找或创建对话
    conv_id = None
    if payload.conversation_id:
        try:
            cid = UUID(payload.conversation_id)
            conv = (await db.execute(select(Conversation).where(Conversation.id == cid, Conversation.user_id == current_user.id))).scalar_one_or_none()
            if conv:
                if campaign_uuid is None or conv.campaign_id == campaign_uuid:
                    conv_id = conv.id
        except ValueError:
            pass

    if not conv_id:
        conv = Conversation(
            user_id=current_user.id,
            workspace=_normalize_workspace(payload.workspace),
            campaign_id=campaign_uuid,
        )
        db.add(conv)
        await db.flush()
        conv_id = conv.id

    # 保存用户消息（对话历史先有用户侧，助手回复由后台执行后补）
    db.add(ConversationMessage(conversation_id=conv_id, role="user", content=payload.instruction))

    # 创建任务记录（pending，由 scheduler 分发后台执行）
    task = AgentTask(
        user_id=current_user.id,
        task_type="agent_run",
        status="pending",
        input=json.dumps({
            "instruction": payload.instruction,
            "conversation_id": str(conv_id),
            "workspace": _normalize_workspace(payload.workspace),
            "campaign_id": campaign_id,
        }, ensure_ascii=False),
        idempotency_key=idempotency_key or None,
        cost=cost,
    )
    db.add(task)
    await db.commit()

    return _task_response(task)


@router.get("/tasks/{task_id}")
async def get_agent_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询 Agent 任务状态（前端轮询用）。

    任务未完成时 status 为 pending/running；完成后为 succeeded/failed，
    带 summary、steps 等最终结果。
    """
    from uuid import UUID
    try:
        tid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的任务ID")

    task = (await db.execute(
        select(AgentTask).where(AgentTask.id == tid, AgentTask.user_id == current_user.id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return _task_response(task)


@router.get("/tasks/{task_id}/stream")
async def stream_agent_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 推流：任务执行过程中实时推送步骤进度，完成时推送最终结果。

    前端用 EventSource 订阅，替代 2s 轮询：
    - `event: step` —— 任务执行中，携带当前已完成的 steps
    - `event: done` —— 任务结束（succeeded 带结果 / failed 带错误）

    实现：轮询 DB 读取中间进度（progress 列）。生产 4 worker 共享同一
    PG，执行器与 SSE 连接可能落在不同进程 → 以 DB 为共享事实源。
    连接断开时生成器被取消，由 get_db 兜底归还会话。
    """
    from uuid import UUID
    try:
        tid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的任务ID")

    task = (await db.execute(
        select(AgentTask).where(AgentTask.id == tid, AgentTask.user_id == current_user.id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_stream():
        last_status = None
        last_step_count = 0
        last_heartbeat = asyncio.get_running_loop().time()
        while True:
            fresh = (await db.execute(
                select(AgentTask).where(AgentTask.id == tid)
            )).scalar_one_or_none()
            if fresh is None:
                yield "event: done\ndata: {\"status\":\"failed\",\"error\":\"任务不存在\"}\n\n"
                return

            changed, event, step_count = _sse_event(fresh, last_status, last_step_count)
            # 释放本轮读事务：长连接不能一直攥着快照/锁（SQLite 单连接下也避免阻塞写入）。
            # 注意：rollback 会让 fresh 过期，必须在 rollback 前把要用的状态快照出来，
            # 否则 yield 之后访问 fresh.status 会触发异步刷新，抛 MissingGreenlet。
            status_now = fresh.status
            await db.rollback()

            if changed:
                yield event
                last_status = status_now
                last_step_count = step_count
                if status_now in ("succeeded", "failed"):
                    return

            # 心跳：防 Nginx/浏览器代理超时断开（15s 一次）
            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= 15:
                yield ": ping\n\n"
                last_heartbeat = now

            await asyncio.sleep(STREAM_POLL_INTERVAL)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 关 Nginx 缓冲，SSE 不被攒住
        },
    )


class WorkflowRequest(BaseModel):
    workflow: str = Field(...)
    url: str = Field("")
    platform: str = Field("amazon")
    language: str = Field("en")


@router.post("/workflow", status_code=status.HTTP_202_ACCEPTED)
async def run_workflow(
    payload: WorkflowRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    """提交预设工作流任务（异步，立即返回 task_id，前端轮询结果）

    积分从工作流模板读（与 /workflows 展示一致）；未知工作流返回 400。
    """
    template = WORKFLOW_TEMPLATES.get(payload.workflow)
    if not template:
        raise HTTPException(status_code=400, detail="未知的工作流，请刷新后重试")
    if not check_feature_access(current_user, "agent"):
        raise HTTPException(status_code=403, detail="AI 智能助手仅限 Standard 及以上套餐使用")
    cost = template["cost"]
    if current_user.credits < cost:
        raise HTTPException(status_code=402, detail="积分不足")

    if idempotency_key:
        existing = (await db.execute(
            select(AgentTask).where(
                AgentTask.user_id == current_user.id,
                AgentTask.idempotency_key == idempotency_key,
            )
        )).scalar_one_or_none()
        if existing:
            return _task_response(existing)

    task = AgentTask(
        user_id=current_user.id,
        task_type="agent_workflow",
        status="pending",
        input=json.dumps({
            "workflow": payload.workflow,
            "params": {"url": payload.url, "platform": payload.platform, "language": payload.language},
        }, ensure_ascii=False),
        idempotency_key=idempotency_key or None,
        cost=cost,
    )
    db.add(task)
    await db.commit()

    return _task_response(task)
