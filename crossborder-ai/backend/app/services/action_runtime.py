"""受控动作运行时。

模型只能选择领域动作，真正的参数校验、权限判断、幂等控制、平台调用和
回读核验由本模块负责。这样退款、发货和发布不会因为模型重试而重复执行。
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_run import ActionRun
from app.models.agent_policy import ActionApproval
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.workspace import Workspace
from app.services.agent_policy import (
    decision_requires_dual_approval,
    evaluate_autonomy,
    get_workspace_member_role,
    workspace_is_paused,
)
from app.services.notifications import create_notification


class ActionRunConflict(ValueError):
    """相同幂等键被用于不同动作参数。"""


class ActionRunStateError(ValueError):
    """动作当前状态不允许继续执行。"""


@dataclass(frozen=True)
class ActionDefinition:
    """代码中注册的领域动作契约。"""

    action_id: str
    version: str
    platform: str
    target_type: str
    risk_level: str
    default_autonomy: str
    requires_confirmation: bool = False


@dataclass
class ActionExecution:
    """适配器执行后的外部对象与用户可读结果。"""

    external_id: str | None
    output: dict | None = None


@dataclass
class ActionVerification:
    """平台回读核验结果。"""

    matched: bool
    snapshot: dict | None = None
    details: dict | None = None
    terminal: bool = True


class ActionAdapter(Protocol):
    """平台适配器必须实现的最小接口。"""

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        """执行前重新读取真实状态并返回快照。"""

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        """执行一个已经通过预检和策略判断的动作。"""

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        """回读平台最终状态，不能只相信写接口返回值。"""


# 首发动作能力。平台接口名不直接暴露给 Agent，避免模型绕过业务规则。
ACTION_DEFINITIONS: dict[str, ActionDefinition] = {
    "operations.scan": ActionDefinition(
        action_id="operations.scan",
        version="1.0",
        platform="internal",
        target_type="workspace",
        risk_level="low",
        default_autonomy="auto",
    ),
    "listings.create": ActionDefinition(
        action_id="listings.create",
        version="1.0",
        platform="shopify",
        target_type="listings",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "listings.update": ActionDefinition(
        action_id="listings.update",
        version="1.0",
        platform="shopify",
        target_type="listings",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "listing.media.attach": ActionDefinition(
        action_id="listing.media.attach",
        version="1.0",
        platform="shopify",
        target_type="listings",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "listings.publish": ActionDefinition(
        action_id="listings.publish",
        version="1.0",
        platform="shopify",
        target_type="product",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.listings.publish": ActionDefinition(
        action_id="amazon.listings.publish",
        version="1.0",
        platform="amazon",
        target_type="product",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.orders.fulfill": ActionDefinition(
        action_id="amazon.orders.fulfill",
        version="1.0",
        platform="amazon",
        target_type="order",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "temu.orders.fulfill": ActionDefinition(
        action_id="temu.orders.fulfill",
        version="1.0",
        platform="temu",
        target_type="order",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "temu.listings.submit": ActionDefinition(
        action_id="temu.listings.submit",
        version="1.0",
        platform="temu",
        target_type="listing",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "temu.inventory.update": ActionDefinition(
        action_id="temu.inventory.update",
        version="1.0",
        platform="temu",
        target_type="listing",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "temu.pricing.submit": ActionDefinition(
        action_id="temu.pricing.submit",
        version="1.0",
        platform="temu",
        target_type="listing",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.inventory.update": ActionDefinition(
        action_id="amazon.inventory.update",
        version="1.0",
        platform="amazon",
        target_type="listing",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.pricing.update": ActionDefinition(
        action_id="amazon.pricing.update",
        version="1.0",
        platform="amazon",
        target_type="listing",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.listings.update": ActionDefinition(
        action_id="amazon.listings.update",
        version="1.0",
        platform="amazon",
        target_type="listing",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.listing.media.attach": ActionDefinition(
        action_id="amazon.listing.media.attach",
        version="1.0",
        platform="amazon",
        target_type="listing",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "amazon.listing.media.attach_assets": ActionDefinition(
        action_id="amazon.listing.media.attach_assets",
        version="1.0",
        platform="amazon",
        target_type="listing",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "orders.fulfill": ActionDefinition(
        action_id="orders.fulfill",
        version="1.0",
        platform="shopify",
        target_type="fulfillment_order",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "orders.delay_notice": ActionDefinition(
        action_id="orders.delay_notice",
        version="1.0",
        platform="shopify",
        target_type="order",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "orders.cancel": ActionDefinition(
        action_id="orders.cancel",
        version="1.0",
        platform="shopify",
        target_type="order",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "refunds.create": ActionDefinition(
        action_id="refunds.create",
        version="1.0",
        platform="shopify",
        target_type="order",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "messages.reply": ActionDefinition(
        action_id="messages.reply",
        version="1.0",
        platform="email",
        target_type="conversation",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "reviews.reply": ActionDefinition(
        action_id="reviews.reply",
        version="1.0",
        platform="shopify",
        target_type="review",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "inventory.update": ActionDefinition(
        action_id="inventory.update",
        version="1.0",
        platform="shopify",
        target_type="inventory_item",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "pricing.update": ActionDefinition(
        action_id="pricing.update",
        version="1.0",
        platform="shopify",
        target_type="product_variant",
        risk_level="high",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "media.generate_image": ActionDefinition(
        action_id="media.generate_image",
        version="1.0",
        platform="internal",
        target_type="media_task",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
    "media.generate_video": ActionDefinition(
        action_id="media.generate_video",
        version="1.0",
        platform="internal",
        target_type="media_task",
        risk_level="medium",
        default_autonomy="confirm",
        requires_confirmation=True,
    ),
}


def get_action_definition(action_id: str) -> ActionDefinition:
    """按稳定领域编号读取动作定义，未知动作一律拒绝。"""

    definition = ACTION_DEFINITIONS.get(action_id)
    if definition is None:
        raise ValueError(f"未知动作：{action_id}")
    return definition


def _json_dump(value: dict | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_event(
    db: AsyncSession,
    *,
    item: WorkItem,
    event_type: str,
    actor_user_id: UUID | None,
    payload: dict,
) -> None:
    """写入工作项时间线事件，调用方负责统一提交事务。"""

    db.add(
        WorkItemEvent(
            workspace_id=item.workspace_id,
            work_item_id=item.id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload_json=_json_dump(payload),
        )
    )


async def _load_item(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    work_item_id: UUID,
) -> WorkItem:
    item = (
        await db.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace_id,
                WorkItem.id == work_item_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise ValueError("工作项不存在")
    return item


async def get_action_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    action_run_id: UUID,
) -> ActionRun | None:
    """按工作区读取动作，跨工作区访问必须返回空。"""

    return (
        await db.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace_id,
                ActionRun.id == action_run_id,
            )
        )
    ).scalar_one_or_none()


async def list_action_runs_for_work_item(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    work_item_id: UUID,
) -> list[ActionRun]:
    """返回工作项下的动作轨迹，供 App 展示进度而不是暴露工具日志。"""

    return (
        await db.execute(
            select(ActionRun)
            .where(
                ActionRun.workspace_id == workspace_id,
                ActionRun.work_item_id == work_item_id,
            )
            .order_by(ActionRun.created_at, ActionRun.id)
        )
    ).scalars().all()


async def plan_action_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    work_item_id: UUID,
    action_id: str,
    platform: str,
    target_type: str,
    target_id: str,
    input_data: dict | None,
    idempotency_key: str,
    autonomy_level: str | None = None,
    agent_turn_id: UUID | None = None,
) -> ActionRun:
    """创建动作计划，重复幂等键返回原记录。"""

    definition = get_action_definition(action_id)
    if platform != definition.platform:
        raise ValueError("动作平台与注册定义不一致")
    if target_type != definition.target_type:
        raise ValueError("动作目标类型与注册定义不一致")

    existing = (
        await db.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == workspace_id,
                ActionRun.action_id == action_id,
                ActionRun.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    normalized_input = input_data or {}
    if existing is not None:
        if (
            existing.work_item_id != work_item_id
            or existing.target_id != target_id
            or existing.input_json != _json_dump(normalized_input)
        ):
            raise ActionRunConflict("相同幂等键对应不同动作请求")
        return existing

    item = await _load_item(
        db,
        workspace_id=workspace_id,
        work_item_id=work_item_id,
    )
    decision = await evaluate_autonomy(
        db,
        workspace_id=workspace_id,
        definition=definition,
        input_data=normalized_input,
        requested_level=autonomy_level,
    )
    selected_autonomy = decision.autonomy_level
    if selected_autonomy not in {"suggest", "confirm", "auto"}:
        raise ValueError("未知自主级别")

    if selected_autonomy == "auto":
        initial_status = "queued"
    elif selected_autonomy == "suggest":
        initial_status = "planned"
    else:
        initial_status = "awaiting_confirmation"

    run = ActionRun(
        workspace_id=workspace_id,
        work_item_id=work_item_id,
        agent_turn_id=agent_turn_id,
        action_id=definition.action_id,
        action_version=definition.version,
        platform=platform,
        target_type=target_type,
        target_id=target_id,
        input_json=_json_dump(normalized_input),
        status=initial_status,
        risk_level=definition.risk_level,
        autonomy_level=selected_autonomy,
        policy_id=decision.policy_id,
        policy_version=decision.policy_version,
        policy_snapshot_json=_json_dump(
            decision.snapshot(definition.action_id)
        ),
        idempotency_key=idempotency_key,
    )
    db.add(run)
    await db.flush()

    if initial_status == "queued":
        item.status = "running"
        item.requires_action = "none"
        item.current_step = "动作已排队"
    elif initial_status == "awaiting_confirmation":
        item.status = "waiting_user"
        item.requires_action = "confirm"
        item.current_step = "等待确认执行"
    else:
        item.status = "waiting_user"
        item.requires_action = "choose"
        item.current_step = "等待选择执行方案"
    item.version += 1
    if initial_status in {"queued", "awaiting_confirmation"}:
        workspace = await db.get(Workspace, workspace_id)
        notify_user_id = (
            (workspace.owner_user_id if workspace else None)
            or actor_user_id
        )
        await create_notification(
            db,
            workspace_id=workspace_id,
            user_id=notify_user_id,
            work_item_id=item.id,
            notification_type=(
                "needs_action"
                if initial_status == "awaiting_confirmation"
                else "action_started"
            ),
            title=(
                "有一件事需要你决定"
                if initial_status == "awaiting_confirmation"
                else "Agent 正在处理一项工作"
            ),
            body="打开 VeyaShip 查看当前进度。",
            deep_link=f"/t/{item.id}?workspaceId={workspace_id}",
            dedupe_key=(
                f"work-item:{item.id}:needs-action"
                if initial_status == "awaiting_confirmation"
                else f"action:{run.id}:started"
            ),
        )
    _add_event(
        db,
        item=item,
        event_type="action_run.planned",
        actor_user_id=actor_user_id,
        payload={
            "action_run_id": str(run.id),
            "action_id": run.action_id,
            "status": run.status,
            "risk_level": run.risk_level,
            "autonomy_level": run.autonomy_level,
            "policy_id": (
                str(run.policy_id) if run.policy_id is not None else None
            ),
            "policy_version": run.policy_version,
            "policy_reason": decision.reason,
        },
    )
    await db.flush()
    return run


async def confirm_action_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    action_run_id: UUID,
    actor_user_id: UUID,
) -> ActionRun:
    """把需要确认的动作转为可执行状态并留下确认人。"""

    run = await get_action_run(
        db,
        workspace_id=workspace_id,
        action_run_id=action_run_id,
    )
    if run is None:
        raise ValueError("动作不存在")
    if run.status not in {"awaiting_confirmation", "planned"}:
        raise ActionRunStateError("动作当前状态不需要确认")

    item = await _load_item(
        db,
        workspace_id=workspace_id,
        work_item_id=run.work_item_id,
    )

    if decision_requires_dual_approval(run):
        role = await get_workspace_member_role(
            db,
            workspace_id=workspace_id,
            user_id=actor_user_id,
        )
        if role not in {"owner", "admin"}:
            raise ActionRunStateError("双人审批只允许所有者或管理员参与")
        existing = (
            await db.execute(
                select(ActionApproval).where(
                    ActionApproval.workspace_id == workspace_id,
                    ActionApproval.action_run_id == run.id,
                )
            )
        ).scalars().all()
        if any(approval.user_id == actor_user_id for approval in existing):
            # 同一确认命令重试时保持幂等，不产生第二条审批记录。
            return run
        db.add(
            ActionApproval(
                workspace_id=workspace_id,
                action_run_id=run.id,
                user_id=actor_user_id,
                role=role,
            )
        )
        await db.flush()
        approval_count = len(existing) + 1
        if approval_count < 2:
            item.status = "waiting_user"
            item.requires_action = "confirm"
            item.current_step = "已获得一人批准，等待另一位管理员确认"
            item.version += 1
            run.version += 1
            _add_event(
                db,
                item=item,
                event_type="action_run.approval_recorded",
                actor_user_id=actor_user_id,
                payload={
                    "action_run_id": str(run.id),
                    "action_id": run.action_id,
                    "approval_count": approval_count,
                    "required": 2,
                },
            )
            await db.flush()
            return run

    run.status = "queued"
    run.confirmed_by_user_id = actor_user_id
    run.confirmed_at = _now()
    run.version += 1
    item.status = "running"
    item.requires_action = "none"
    item.current_step = "动作已确认，等待执行"
    item.version += 1
    _add_event(
        db,
        item=item,
        event_type="action_run.confirmed",
        actor_user_id=actor_user_id,
        payload={
            "action_run_id": str(run.id),
            "action_id": run.action_id,
            "dual_approval": decision_requires_dual_approval(run),
        },
    )
    await db.flush()
    return run


async def retry_action_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    action_run_id: UUID,
    actor_user_id: UUID,
) -> ActionRun:
    """允许用户重试失败动作，但保留原运行记录和尝试次数。"""

    run = await get_action_run(
        db,
        workspace_id=workspace_id,
        action_run_id=action_run_id,
    )
    if run is None:
        raise ValueError("动作不存在")
    if run.status not in {"retryable_failed", "blocked"}:
        raise ActionRunStateError("动作当前状态不允许重试")

    item = await _load_item(
        db,
        workspace_id=workspace_id,
        work_item_id=run.work_item_id,
    )
    run.status = "queued"
    run.error_code = None
    if run.action_id in {"media.generate_image", "media.generate_video"}:
        base_key = run.idempotency_key.split(":retry:", 1)[0]
        run.idempotency_key = f"{base_key}:retry:{run.attempt + 1}"
        run.external_id = None
        run.before_snapshot_json = None
        run.after_snapshot_json = None
        run.verification_json = None
    run.version += 1
    item.status = "running"
    item.requires_action = "none"
    item.current_step = "动作已重新排队"
    item.version += 1
    _add_event(
        db,
        item=item,
        event_type="action_run.retry_queued",
        actor_user_id=actor_user_id,
        payload={"action_run_id": str(run.id), "action_id": run.action_id},
    )
    await db.flush()
    return run


async def execute_action_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    action_run_id: UUID,
    adapter: ActionAdapter,
) -> ActionRun:
    """执行一个已排队动作，并在完成后强制回读核验。"""

    run = await get_action_run(
        db,
        workspace_id=workspace_id,
        action_run_id=action_run_id,
    )
    if run is None:
        raise ValueError("动作不存在")
    if run.status == "succeeded":
        return run
    if run.status == "awaiting_confirmation":
        raise ActionRunStateError("动作尚未确认")
    if run.status in {"executing", "verifying"}:
        raise ActionRunStateError("动作正在执行")
    if run.status not in {"queued", "retryable_failed"}:
        raise ActionRunStateError("动作当前状态不允许执行")

    item = await _load_item(
        db,
        workspace_id=workspace_id,
        work_item_id=run.work_item_id,
    )
    workspace = await db.get(Workspace, workspace_id)
    if (
        run.autonomy_level == "auto"
        and workspace_is_paused(workspace)
    ):
        run.status = "blocked"
        run.error_code = "agent_paused"
        run.verification_json = _json_dump(
            {"error": "工作区已暂停 Agent 自动执行"}
        )
        run.version += 1
        item.status = "waiting_user"
        item.requires_action = "retry"
        item.current_step = "Agent 已暂停，恢复后可重新排队"
        item.version += 1
        _add_event(
            db,
            item=item,
            event_type="action_run.paused",
            actor_user_id=run.confirmed_by_user_id,
            payload={
                "action_run_id": str(run.id),
                "action_id": run.action_id,
            },
        )
        await db.flush()
        return run

    input_data = _json_load(run.input_json)
    run.status = "preflight"
    run.version += 1
    await db.flush()

    try:
        before_snapshot = await adapter.preflight(
            action_id=run.action_id,
            target_id=run.target_id,
            input_data=input_data,
        )
        run.before_snapshot_json = _json_dump(before_snapshot)
        run.status = "executing"
        run.attempt += 1
        run.started_at = _now()
        run.finished_at = None
        run.error_code = None
        run.version += 1
        item.status = "running"
        item.current_step = "动作正在执行"
        item.version += 1
        _add_event(
            db,
            item=item,
            event_type="action_run.started",
            actor_user_id=run.confirmed_by_user_id,
            payload={
                "action_run_id": str(run.id),
                "action_id": run.action_id,
                "attempt": run.attempt,
            },
        )
        await db.flush()

        execution = await adapter.execute(
            action_id=run.action_id,
            target_id=run.target_id,
            input_data=input_data,
            idempotency_key=run.idempotency_key,
        )
        run.external_id = execution.external_id
        run.status = "verifying"
        run.version += 1
        item.current_step = "动作已提交，正在回读核验"
        item.version += 1
        await db.flush()

        verification = await adapter.verify(
            action_id=run.action_id,
            target_id=run.target_id,
            execution=execution,
        )
        run.verification_json = _json_dump(verification.details or {})
        run.after_snapshot_json = _json_dump(verification.snapshot or {})
        run.finished_at = _now()
        run.version += 1
        if verification.matched and verification.terminal:
            run.status = "succeeded"
            item.status = "succeeded"
            item.requires_action = "none"
            item.current_step = "动作已完成并核验"
            event_type = "action_run.succeeded"
        elif verification.matched:
            run.status = "verifying"
            item.status = "running"
            item.requires_action = "none"
            item.current_step = "外部任务已提交，等待结果回写"
            event_type = "action_run.awaiting_result"
        else:
            run.status = "blocked"
            run.error_code = "verification_mismatch"
            item.status = "waiting_user"
            item.requires_action = "retry"
            item.current_step = "动作执行后回读不一致，请重试"
            event_type = "action_run.blocked"
        if not verification.matched:
            workspace = await db.get(Workspace, workspace_id)
            notify_user_id = (
                run.confirmed_by_user_id
                or (workspace.owner_user_id if workspace else None)
            )
            if notify_user_id is not None:
                await create_notification(
                    db,
                    workspace_id=workspace_id,
                    user_id=notify_user_id,
                    work_item_id=item.id,
                    notification_type="action_failed",
                    title="有一项操作失败",
                    body="打开 VeyaShip 查看原因和恢复方式。",
                    deep_link=f"/t/{item.id}?workspaceId={workspace_id}",
                    dedupe_key=f"action:{run.id}:failed",
                )
        item.version += 1
        _add_event(
            db,
            item=item,
            event_type=event_type,
            actor_user_id=run.confirmed_by_user_id,
            payload={
                "action_run_id": str(run.id),
                "action_id": run.action_id,
                "external_id": run.external_id,
                "matched": verification.matched,
            },
        )
        await db.flush()
        return run
    except Exception as exc:
        # 适配器异常不能把动作伪装成成功，保留原始记录供重试和审计。
        run.status = "retryable_failed"
        run.error_code = "adapter_error"
        run.verification_json = _json_dump({"error": str(exc)[:500]})
        run.finished_at = _now()
        run.version += 1
        item.status = "waiting_user"
        item.requires_action = "retry"
        item.current_step = "动作执行失败，可重试"
        item.version += 1
        workspace = await db.get(Workspace, workspace_id)
        notify_user_id = (
            run.confirmed_by_user_id
            or (workspace.owner_user_id if workspace else None)
        )
        if notify_user_id is not None:
            await create_notification(
                db,
                workspace_id=workspace_id,
                user_id=notify_user_id,
                work_item_id=item.id,
                notification_type="action_failed",
                title="有一项操作失败",
                body="打开 VeyaShip 查看原因和恢复方式。",
                deep_link=f"/t/{item.id}?workspaceId={workspace_id}",
                dedupe_key=f"action:{run.id}:failed",
            )
        _add_event(
            db,
            item=item,
            event_type="action_run.retryable_failed",
            actor_user_id=run.confirmed_by_user_id,
            payload={
                "action_run_id": str(run.id),
                "action_id": run.action_id,
                "error": str(exc)[:500],
            },
        )
        await db.flush()
        raise
