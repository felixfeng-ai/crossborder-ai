"""工作项创建、读取与用户命令服务。"""

import hashlib
import json
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_work import WorkItem, WorkItemCommand, WorkItemEvent
from app.models.workspace import Workspace
from app.services.agent_result_state import result_needs_user_input
from app.services.notifications import create_notification
from app.services.action_runtime import ACTION_DEFINITIONS, plan_action_run
from app.services.business_time import business_day_utc_bounds


class WorkItemVersionConflict(ValueError):
    """工作项版本已变化。"""


class WorkItemCommandConflict(ValueError):
    """相同幂等键对应不同请求。"""


class WorkItemStateError(ValueError):
    """工作项当前状态不允许该命令。"""


def _payload_json(payload: dict | None) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)


def _request_hash(
    *,
    action: str,
    expected_version: int,
    payload: dict | None,
) -> str:
    raw = json.dumps(
        {
            "action": action,
            "expected_version": expected_version,
            "payload": payload or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def create_work_item(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None,
    kind: str,
    source: str,
    title: str,
    summary: str = "",
    priority: str = "normal",
    requires_action: str = "none",
    status: str = "waiting_user",
    current_step: str | None = None,
    due_at: datetime | None = None,
    expires_at: datetime | None = None,
    assignee_user_id: UUID | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    source_version: str | None = None,
    channel_type: str | None = None,
    channel_id: str | None = None,
    result: dict | None = None,
) -> WorkItem:
    item = WorkItem(
        workspace_id=workspace_id,
        kind=kind,
        source=source,
        title=title,
        summary=summary,
        priority=priority,
        requires_action=requires_action,
        status=status,
        current_step=current_step
        or ("等待你决定" if requires_action != "none" else "等待处理"),
        due_at=due_at,
        expires_at=expires_at,
        assignee_user_id=assignee_user_id,
        source_type=source_type,
        source_id=source_id,
        source_version=source_version,
        channel_type=channel_type,
        channel_id=channel_id,
        result_json=_payload_json(result) if result is not None else None,
    )
    db.add(item)
    await db.flush()
    if requires_action != "none" and status == "waiting_user":
        workspace = await db.get(Workspace, workspace_id)
        notify_user_id = (
            assignee_user_id
            or (workspace.owner_user_id if workspace else None)
            or actor_user_id
        )
        if notify_user_id is not None:
            await create_notification(
                db,
                workspace_id=workspace_id,
                user_id=notify_user_id,
                work_item_id=item.id,
                notification_type="needs_action",
                title="有一件事需要你决定",
                body="打开 VeyaShip 查看 Agent 准备好的处理方案。",
                deep_link=f"/t/{item.id}?workspaceId={workspace_id}",
                dedupe_key=f"work-item:{item.id}:needs-action",
            )
    db.add(
        WorkItemEvent(
            workspace_id=workspace_id,
            work_item_id=item.id,
            event_type="work_item.created",
            actor_user_id=actor_user_id,
            payload_json=_payload_json(
                {
                    "status": item.status,
                    "priority": item.priority,
                    "requires_action": item.requires_action,
                }
            ),
        )
    )
    await db.flush()
    return item


async def get_work_item(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    work_item_id: UUID,
) -> WorkItem | None:
    return (
        await db.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace_id,
                WorkItem.id == work_item_id,
            )
        )
    ).scalar_one_or_none()


async def list_work_items_for_date(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    business_date: date,
    timezone_name: str = "Asia/Shanghai",
    channel_type: str | None = None,
    channel_id: str | None = None,
) -> list[WorkItem]:
    start, end = business_day_utc_bounds(business_date, timezone_name)
    priority_order = case(
        (WorkItem.priority == "urgent", 0),
        (WorkItem.priority == "attention", 1),
        else_=2,
    )
    filters = [
        WorkItem.workspace_id == workspace_id,
        WorkItem.created_at >= start,
        WorkItem.created_at < end,
    ]
    if channel_type and channel_id:
        filters.extend(
            [
                WorkItem.channel_type == channel_type,
                WorkItem.channel_id == channel_id,
            ]
        )
    return (
        await db.execute(
            select(WorkItem)
            .where(*filters)
            .order_by(priority_order, WorkItem.created_at)
        )
    ).scalars().all()


async def submit_work_item_command(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    work_item_id: UUID,
    actor_user_id: UUID,
    action: str,
    expected_version: int,
    payload: dict | None,
    idempotency_key: str,
) -> WorkItemCommand:
    existing = (
        await db.execute(
            select(WorkItemCommand).where(
                WorkItemCommand.workspace_id == workspace_id,
                WorkItemCommand.actor_user_id == actor_user_id,
                WorkItemCommand.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    request_hash = _request_hash(
        action=action,
        expected_version=expected_version,
        payload=payload,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise WorkItemCommandConflict("相同幂等键对应不同请求")
        return existing

    item = await get_work_item(
        db,
        workspace_id=workspace_id,
        work_item_id=work_item_id,
    )
    if item is None:
        raise ValueError("工作项不存在")
    if item.version != expected_version:
        raise WorkItemVersionConflict("工作项已被其他人处理")
    if item.status != "waiting_user" or item.requires_action == "none":
        raise WorkItemStateError("工作项当前不需要该动作")
    if item.requires_action != action:
        raise WorkItemStateError("动作与工作项要求不一致")

    command = WorkItemCommand(
        workspace_id=workspace_id,
        work_item_id=work_item_id,
        actor_user_id=actor_user_id,
        action=action,
        payload_json=_payload_json(payload),
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        status="accepted",
        processed_at=None,
    )
    db.add(command)
    await db.flush()

    item.status = "running"
    item.requires_action = "none"
    item.current_step = "Agent 正在执行"
    item.version += 1
    db.add(
        WorkItemEvent(
            workspace_id=workspace_id,
            work_item_id=work_item_id,
            event_type="work_item.command.accepted",
            actor_user_id=actor_user_id,
            payload_json=_payload_json(
                {
                    "action": action,
                    "command_id": str(command.id),
                    "version": item.version,
                }
            ),
        )
    )
    await db.flush()
    return command


async def complete_work_item_from_agent_task(
    db: AsyncSession,
    *,
    agent_task_id: UUID,
    status: str,
    summary: str,
    error: str | None,
    task_result: dict | None = None,
) -> WorkItem | None:
    """把技术任务结果同步到用户可见的工作项。

    Agent 执行记录与工作项分开保存：这里只更新与 agent_task 关联的工作项，
    不改动其他任务，也不负责提交事务，由任务执行器统一提交。
    """

    item = (
        await db.execute(
            select(WorkItem).where(
                WorkItem.source_type == "agent_task",
                WorkItem.source_id == str(agent_task_id),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        return None

    succeeded = status == "succeeded"
    needs_user_input = succeeded and result_needs_user_input(task_result)
    if needs_user_input:
        next_status = "waiting_user"
        next_step = "等待你补充信息"
        next_action = "input"
    else:
        next_status = "succeeded" if succeeded else "failed"
        next_step = "已完成" if succeeded else "处理失败，可重试"
        next_action = "none" if succeeded else "retry"
    next_result = _payload_json({"summary": summary, "error": error})
    changed = any((
        item.status != next_status,
        item.current_step != next_step,
        item.requires_action != next_action,
        item.result_json != next_result,
    ))
    if not changed:
        return item

    item.status = next_status
    item.current_step = next_step
    item.requires_action = next_action
    item.result_json = next_result
    item.version += 1

    db.add(
        WorkItemEvent(
            workspace_id=item.workspace_id,
            work_item_id=item.id,
            event_type=(
                "work_item.agent_task.needs_input"
                if needs_user_input
                else (
                    "work_item.agent_task.succeeded"
                    if succeeded
                    else "work_item.agent_task.failed"
                )
            ),
            payload_json=_payload_json(
                {
                    "agent_task_id": str(agent_task_id),
                    "summary": summary,
                    "error": error,
                    "version": item.version,
                }
            ),
        )
    )
    await db.flush()
    return item


async def create_work_items_from_agent_result(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None,
    agent_task_id: UUID,
    result: dict,
) -> list[WorkItem]:
    """把 Agent 返回的结构化待确认动作落成用户可操作工作项。

    不直接执行工具，只保存待确认动作；真正的执行仍由动作运行时和用户命令
    控制，避免模型结果绕过权限与确认。
    """

    pending_actions: list[dict] = []
    candidates = []
    if isinstance(result.get("pending_action"), dict):
        candidates.append(result["pending_action"])
    top_level_data = result.get("data")
    if isinstance(top_level_data, dict) and isinstance(
        top_level_data.get("pending_action"),
        dict,
    ):
        candidates.append(top_level_data["pending_action"])
    for step in result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        data = step.get("data")
        if isinstance(data, dict) and isinstance(
            data.get("pending_action"),
            dict,
        ):
            candidates.append(data["pending_action"])
        if isinstance(step.get("pending_action"), dict):
            candidates.append(step["pending_action"])

    seen: set[str] = set()
    for pending in candidates:
        action = str(pending.get("action") or "").strip()
        params = pending.get("params")
        if not action or not isinstance(params, dict):
            continue
        raw = _payload_json({"action": action, "params": params})
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        pending_actions.append(
            {
                "action": action,
                "params": params,
                "estimated_credits": pending.get("estimated_credits"),
                "fingerprint": fingerprint,
            }
        )

    action_labels = {
        "generate_product_image": "确认生成商品图片",
        "generate_image_asset": "确认生成商品图片",
        "generate_product_video": "确认生成商品视频",
        "push_to_shopify": "确认发布商品到 Shopify",
        "listings.publish": "确认发布商品",
        "orders.fulfill": "确认订单履约",
        "refunds.create": "确认退款",
        "messages.reply": "确认发送客户回复",
        "reviews.reply": "确认发布评价回复",
        "pricing.update": "确认修改销售价",
        "inventory.update": "确认更新库存",
        "listings.update": "确认更新商品内容",
        "orders.cancel": "确认取消订单",
        "listing.media.attach": "确认附加商品图片",
        "amazon.listings.publish": "确认发布到 Amazon",
        "amazon.orders.fulfill": "确认 Amazon 发货",
        "amazon.inventory.update": "确认更新 Amazon 库存",
        "amazon.pricing.update": "确认修改 Amazon 售价",
        "amazon.listings.update": "确认更新 Amazon Listing",
        "amazon.listing.media.attach": "确认绑定 Amazon Listing 图片",
        "amazon.listing.media.attach_assets": "确认发布并绑定 Amazon 图片",
    }
    created: list[WorkItem] = []
    action_aliases = {
        "push_to_shopify": "listings.publish",
        "generate_product_image": "media.generate_image",
        "generate_image_asset": "media.generate_image",
        "generate_product_video": "media.generate_video",
    }
    for pending in pending_actions:
        source_id = f"{agent_task_id}:{pending['fingerprint']}"
        existing = (
            await db.execute(
                select(WorkItem).where(
                    WorkItem.workspace_id == workspace_id,
                    WorkItem.source_type == "agent_pending_action",
                    WorkItem.source_id == source_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            created.append(existing)
            continue
        estimated = pending.get("estimated_credits")
        summary = (
            f"Agent 已准备操作，预计消耗 {estimated} 积分，请确认后执行。"
            if estimated is not None
            else "Agent 已准备操作，请确认后执行。"
        )
        item = await create_work_item(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            kind="agent_action",
            source="agent",
            title=action_labels.get(
                pending["action"],
                "确认 Agent 准备的操作",
            ),
            summary=summary,
            status="waiting_user",
            requires_action="confirm",
            current_step="等待你确认 Agent 准备的操作",
            source_type="agent_pending_action",
            source_id=source_id,
            result={"pending_action": pending},
        )
        action_id = action_aliases.get(
            pending["action"],
            pending["action"],
        )
        definition = ACTION_DEFINITIONS.get(action_id)
        params = pending["params"]
        target_keys = (
            "listing_id",
            "product_id",
            "order_id",
            "thread_id",
            "review_id",
            "inventory_item_id",
            "variant_id",
            "target_id",
        )
        if action_id in {"listings.update", "listing.media.attach"}:
            target_keys = ("listing_id",) + tuple(
                key for key in target_keys if key != "listing_id"
            )
        elif action_id in {"pricing.update", "inventory.update"}:
            target_keys = ("variant_id",) + tuple(
                key for key in target_keys if key != "variant_id"
            )
        target_id = next(
            (
                str(params[key])
                for key in target_keys
                if params.get(key)
            ),
            None,
        )
        if definition is not None and definition.target_type == "media_task":
            target_id = str(agent_task_id)
        if definition is not None and target_id:
            await plan_action_run(
                db,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id or workspace_id,
                work_item_id=item.id,
                action_id=action_id,
                platform=definition.platform,
                target_type=definition.target_type,
                target_id=target_id,
                input_data=params,
                idempotency_key=f"agent-pending:{agent_task_id}:{pending['fingerprint']}",
            )
        created.append(item)
    return created
