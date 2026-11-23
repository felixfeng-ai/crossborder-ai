"""Agent 自动值班：领取客服工作项并生成受控回复草稿。"""

import hashlib
import json
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_run import ActionRun
from app.models.agent_task import AgentTask
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.customer_channel import (
    CustomerMessage,
    CustomerOrderLink,
    CustomerThread,
    ReplyDraft,
)
from app.models.workspace import Workspace
from app.services.action_runtime import plan_action_run
from app.services.ai.deepseek import DeepSeekService
from app.services.customer_intent import (
    CustomerRiskAssessment,
    classify_customer_message,
)
from app.services.customer_reply_adapter import create_reply_draft
from app.services.customer_order_link import (
    ShopifyOrderClient,
    resolve_customer_order,
)


class CustomerReplyGenerator(Protocol):
    async def generate(
        self,
        *,
        customer_message: str,
        language: str,
        intent: str,
        current_step: str,
        facts: dict,
    ) -> str:
        """生成可编辑回复；不得编造未提供的事实。"""


class DeepSeekCustomerReplyGenerator:
    """默认客服草稿生成器，只负责表达，不负责查询或执行平台动作。"""

    async def generate(
        self,
        *,
        customer_message: str,
        language: str,
        intent: str,
        current_step: str,
        facts: dict,
    ) -> str:
        service = DeepSeekService()
        body = await service.generate(
            system_prompt=(
                "你是跨境店铺客服回复生成器。只使用用户消息和事实 JSON 中"
                "明确存在的信息，不得编造物流时间、库存、退款、赔偿、折扣或"
                "送达承诺。缺少订单、物流或售后事实时，可以礼貌询问必要信息。"
                "回复要简洁、专业、自然，与客户消息使用同一语言。"
                "只输出可以直接发送的回复正文，不要标题、解释或 Markdown。"
            ),
            user_prompt=(
                f"目标语言：{language}\n"
                f"客户意图：{intent}\n"
                f"当前处理阶段：{current_step}\n"
                f"可用事实：{json.dumps(facts, ensure_ascii=False)}\n"
                f"客户原话：{customer_message}"
            ),
            temperature=0.2,
        )
        normalized = str(body or "").strip()
        if not normalized:
            raise ValueError("回复生成器没有返回可用内容")
        return normalized[:12000]


def _item_result(item: WorkItem) -> dict:
    try:
        parsed = json.loads(item.result_json or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _assessment(
    item: WorkItem,
    *,
    thread: CustomerThread,
    message: CustomerMessage,
) -> CustomerRiskAssessment:
    result = _item_result(item)
    if result.get("risk_level") and result.get("intent"):
        return CustomerRiskAssessment(
            intent=str(result["intent"]),
            risk_level=str(result["risk_level"]),
            priority=str(result.get("priority") or item.priority),
            auto_reply_candidate=bool(
                result.get("auto_reply_candidate", False)
            ),
            requires_human=bool(
                result.get("requires_human", item.priority == "urgent")
            ),
            reasons=tuple(result.get("reasons") or []),
        )
    return classify_customer_message(
        message.body_text,
        is_review=thread.thread_type == "review",
    )


def _task_key(item: WorkItem, message: CustomerMessage) -> str:
    source = str(message.external_message_id or message.id)
    digest = hashlib.sha256(
        f"{item.id}:{source}".encode("utf-8")
    ).hexdigest()[:40]
    return f"customer-reply:{digest}"


async def _latest_inbound(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    thread_id: UUID,
) -> CustomerMessage | None:
    return (
        await db.execute(
            select(CustomerMessage)
            .where(
                CustomerMessage.workspace_id == workspace_id,
                CustomerMessage.thread_id == thread_id,
                CustomerMessage.direction == "inbound",
            )
            .order_by(CustomerMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def enqueue_customer_reply_tasks(
    db: AsyncSession,
    *,
    limit: int = 20,
) -> int:
    """把待自动处理的客户回复工作项写入现有 AgentTask 队列。"""

    items = (
        await db.execute(
            select(WorkItem)
            .where(
                WorkItem.kind == "customer_reply",
                WorkItem.status == "running",
                WorkItem.requires_action == "none",
                WorkItem.source_type == "customer_thread",
                WorkItem.source_id.is_not(None),
                WorkItem.assignee_user_id.is_(None),
            )
            .order_by(WorkItem.created_at)
            .limit(max(1, limit))
        )
    ).scalars().all()
    created = 0
    for item in items:
        result = _item_result(item)
        if result.get("requires_human") or result.get("risk_level") == "high":
            continue
        try:
            thread_id = UUID(str(item.source_id))
        except (TypeError, ValueError):
            continue
        thread = (
            await db.execute(
                select(CustomerThread).where(
                    CustomerThread.id == thread_id,
                    CustomerThread.workspace_id == item.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if (
            thread is None
            or thread.assigned_user_id is not None
        ):
            continue
        message = await _latest_inbound(
            db,
            workspace_id=item.workspace_id,
            thread_id=thread.id,
        )
        if message is None:
            continue
        workspace = await db.get(Workspace, item.workspace_id)
        if workspace is None:
            continue
        key = _task_key(item, message)
        existing = (
            await db.execute(
                select(AgentTask).where(
                    AgentTask.user_id == workspace.owner_user_id,
                    AgentTask.workspace_id == item.workspace_id,
                    AgentTask.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.status in {"failed", "cancelled", "succeeded"}
                and item.status == "running"
            ):
                existing.input = json.dumps(
                    {
                        "workspace_id": str(item.workspace_id),
                        "work_item_id": str(item.id),
                        "thread_id": str(thread.id),
                    },
                    ensure_ascii=False,
                )
                existing.workspace_id = item.workspace_id
                existing.status = "pending"
                existing.progress = None
                existing.result = None
                existing.error = None
                existing.started_at = None
                existing.finished_at = None
                existing.attempt += 1
                created += 1
            continue
        db.add(
            AgentTask(
                user_id=workspace.owner_user_id,
                workspace_id=item.workspace_id,
                task_type="customer_reply",
                status="pending",
                input=json.dumps(
                    {
                        "workspace_id": str(item.workspace_id),
                        "work_item_id": str(item.id),
                        "thread_id": str(thread.id),
                    },
                    ensure_ascii=False,
                ),
                idempotency_key=key,
                cost=0,
            )
        )
        item.current_step = "Agent 正在生成客户回复草稿"
        item.version += 1
        db.add(
            WorkItemEvent(
                workspace_id=item.workspace_id,
                work_item_id=item.id,
                event_type="customer_reply.queued",
                actor_user_id=workspace.owner_user_id,
                payload_json=json.dumps(
                    {
                        "thread_id": str(thread.id),
                        "idempotency_key": key,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        created += 1
    await db.flush()
    return created


def _source_message_key(message: CustomerMessage) -> str:
    return str(message.external_message_id or message.id)


def _existing_draft_for_message(
    drafts: list[ReplyDraft],
    message: CustomerMessage,
) -> ReplyDraft | None:
    source_key = _source_message_key(message)
    for draft in drafts:
        try:
            policy = json.loads(draft.policy_result_json or "{}")
        except json.JSONDecodeError:
            policy = {}
        if (
            isinstance(policy, dict)
            and policy.get("source_message_id") == source_key
            and draft.status not in {"stale", "rejected"}
        ):
            return draft
    return None


def _facts(
    *,
    thread: CustomerThread,
    item: WorkItem,
    assessment: CustomerRiskAssessment,
    order_link: CustomerOrderLink | None,
) -> dict:
    order_fact = None
    if order_link is not None:
        order_fact = {
            "external_order_id": order_link.external_order_id,
            "order_name": order_link.order_name,
            "financial_status": order_link.financial_status,
            "fulfillment_status": order_link.fulfillment_status,
            "tracking_company": order_link.tracking_company,
            "tracking_number": order_link.tracking_number,
            "tracking_url": order_link.tracking_url,
        }
    return {
        "channel": "email",
        "subject": thread.subject,
        "intent": assessment.intent,
        "risk_level": assessment.risk_level,
        "related_order_id": thread.related_order_id,
        "order_fact": order_fact,
        "related_product_id": thread.related_product_id,
        "has_order_fact": bool(thread.related_order_id),
        "work_item_current_step": item.current_step,
    }


async def process_customer_reply_work_item(
    db: AsyncSession,
    *,
    work_item_id: UUID,
    generator: CustomerReplyGenerator | None = None,
    order_client: ShopifyOrderClient | None = None,
) -> dict:
    """为一个工作项生成或复用草稿，并创建幂等受控动作。"""

    item = await db.get(WorkItem, work_item_id)
    if item is None or item.kind != "customer_reply":
        raise ValueError("客服回复工作项不存在")
    try:
        thread_id = UUID(str(item.source_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("客服工作项缺少有效会话") from exc
    thread = (
        await db.execute(
            select(CustomerThread).where(
                CustomerThread.id == thread_id,
                CustomerThread.workspace_id == item.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise ValueError("客户会话不存在")
    if thread.assigned_user_id is not None:
        item.status = "waiting_user"
        item.requires_action = "none"
        item.current_step = "会话已由人工接管，Agent 不再回复"
        item.version += 1
        await db.flush()
        return {"status": "manual_takeover"}

    message = await _latest_inbound(
        db,
        workspace_id=item.workspace_id,
        thread_id=thread.id,
    )
    if message is None:
        raise ValueError("客户会话没有入站消息")
    assessment = _assessment(
        item,
        thread=thread,
        message=message,
    )
    if assessment.requires_human or assessment.risk_level == "high":
        item.status = "waiting_user"
        item.requires_action = "none"
        item.current_step = "高风险客户消息需要人工接管"
        item.priority = "urgent"
        item.version += 1
        await db.flush()
        return {"status": "requires_human"}

    order_link = (
        await db.execute(
            select(CustomerOrderLink).where(
                CustomerOrderLink.workspace_id == item.workspace_id,
                CustomerOrderLink.thread_id == thread.id,
            )
        )
    ).scalar_one_or_none()
    order_lookup_status = "linked" if order_link is not None else "not_attempted"
    order_candidate_count = 1 if order_link is not None else 0
    resolution_candidates: list[dict] = []
    if (
        order_link is None
        and assessment.intent in {"shipping", "order_status", "delivery_delay"}
    ):
        try:
            resolution = await resolve_customer_order(
                db,
                workspace_id=item.workspace_id,
                thread=thread,
                client=order_client,
            )
            order_lookup_status = resolution.status
            order_candidate_count = resolution.candidate_count
            resolution_candidates = list(resolution.candidates)
            if resolution.status == "linked":
                order_link = (
                    await db.execute(
                        select(CustomerOrderLink).where(
                            CustomerOrderLink.workspace_id == item.workspace_id,
                            CustomerOrderLink.thread_id == thread.id,
                        )
                    )
                ).scalar_one()
        except Exception:
            # 平台查询失败只降级为人工确认，不能冒充已读取物流。
            order_lookup_status = "lookup_failed"
            order_candidate_count = 0
    item_result = _item_result(item)
    item_result.update(
        {
            "order_lookup_status": order_lookup_status,
            "order_candidate_count": order_candidate_count,
        }
    )
    if order_lookup_status == "ambiguous":
        item_result["order_candidates"] = resolution_candidates
        item.result_json = json.dumps(item_result, ensure_ascii=False)
        item.status = "waiting_user"
        item.requires_action = "choose"
        item.priority = "attention"
        item.current_step = "匹配到多个订单，请选择正确订单"
        item.version += 1
        db.add(
            WorkItemEvent(
                workspace_id=item.workspace_id,
                work_item_id=item.id,
                event_type="customer_order.choice_required",
                actor_user_id=None,
                payload_json=json.dumps(
                    {
                        "candidate_count": order_candidate_count,
                        "thread_id": str(thread.id),
                    },
                    ensure_ascii=False,
                ),
            )
        )
        await db.flush()
        return {
            "status": "choose_order",
            "candidate_count": order_candidate_count,
        }
    item.result_json = json.dumps(item_result, ensure_ascii=False)

    drafts = (
        await db.execute(
            select(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == item.workspace_id,
                ReplyDraft.thread_id == thread.id,
            )
            .order_by(ReplyDraft.version.desc())
            .limit(10)
        )
    ).scalars().all()
    draft = _existing_draft_for_message(drafts, message)
    if draft is None:
        try:
            body = await (generator or DeepSeekCustomerReplyGenerator()).generate(
                customer_message=message.body_text,
                language=thread.language or "en",
                intent=assessment.intent,
                current_step=item.current_step,
                facts=_facts(
                    thread=thread,
                    item=item,
                    assessment=assessment,
                    order_link=order_link,
                ),
            )
            draft = await create_reply_draft(
                db,
                workspace_id=item.workspace_id,
                thread_id=thread.id,
                body_text=body,
                language=thread.language or "en",
                risk_level=assessment.risk_level,
                agent_run_id=None,
                source_language=None,
            )
            draft.policy_result_json = json.dumps(
                {
                    "source_message_id": _source_message_key(message),
                    "intent": assessment.intent,
                    "risk_level": assessment.risk_level,
                    "generated_by": "customer_reply_worker",
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            item.status = "waiting_user"
            item.requires_action = "retry"
            item.current_step = "回复草稿生成失败，可重试"
            item.version += 1
            db.add(
                WorkItemEvent(
                    workspace_id=item.workspace_id,
                    work_item_id=item.id,
                    event_type="customer_reply.failed",
                    actor_user_id=None,
                    payload_json=json.dumps(
                        {"error": str(exc)[:500]},
                        ensure_ascii=False,
                    ),
                )
            )
            await db.flush()
            raise

    existing_run = (
        await db.execute(
            select(ActionRun)
            .where(
                ActionRun.workspace_id == item.workspace_id,
                ActionRun.work_item_id == item.id,
                ActionRun.action_id == "messages.reply",
            )
            .order_by(ActionRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_run is not None:
        return {"status": existing_run.status, "draft_id": str(draft.id)}

    auto_eligible = (
        assessment.risk_level == "low"
        and assessment.auto_reply_candidate
        and assessment.intent
        in {"pre_sale", "shipping", "order_status"}
    )
    if assessment.intent in {"shipping", "order_status"}:
        auto_eligible = auto_eligible and order_link is not None

    run = await plan_action_run(
        db,
        workspace_id=item.workspace_id,
        actor_user_id=(
            await _workspace_owner_id(db, item.workspace_id)
        ),
        work_item_id=item.id,
        action_id="messages.reply",
        platform="email",
        target_type="conversation",
        target_id=str(thread.id),
        input_data={
            "channel_id": str(thread.channel_id),
            "thread_id": str(thread.id),
            "draft_id": str(draft.id),
            "to": "当前客户会话",
            "subject": thread.subject,
            "language": thread.language,
            "body_text": draft.body_text,
        },
        idempotency_key=(
            f"customer-reply:{item.id}:"
            f"{hashlib.sha256(_source_message_key(message).encode('utf-8')).hexdigest()[:20]}"
        ),
        autonomy_level=None if auto_eligible else "confirm",
    )
    return {"status": run.status, "draft_id": str(draft.id)}


async def _workspace_owner_id(
    db: AsyncSession,
    workspace_id: UUID,
) -> UUID:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("工作区不存在")
    return workspace.owner_user_id
