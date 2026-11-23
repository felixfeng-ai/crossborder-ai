"""确定性的工作区 Agent 自主策略引擎。"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_run import ActionRun
from app.models.agent_policy import AgentAutonomyPolicy
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.workspace import Workspace, WorkspaceAuditLog, WorkspaceMember

if TYPE_CHECKING:
    from app.services.action_runtime import ActionDefinition


AUTONOMY_LEVELS = ("suggest", "confirm", "auto")
CONDITION_KEYS = {
    "max_amount",
    "max_percent",
    "max_quantity",
    "min_margin_percent",
    "max_daily_actions",
    "allow_high_risk",
    "requires_dual_approval",
}


@dataclass(frozen=True)
class AutonomyDecision:
    """策略判断结果，既决定状态，也保留可审计依据。"""

    autonomy_level: str
    allowed: bool
    reason: str
    policy_id: UUID | None = None
    policy_version: int | None = None
    conditions: dict | None = None
    paused: bool = False
    requires_dual_approval: bool = False

    def snapshot(self, action_id: str) -> dict:
        return {
            "action_id": action_id,
            **asdict(self),
            "policy_id": (
                str(self.policy_id) if self.policy_id is not None else None
            ),
        }


def normalize_conditions(raw: dict | None) -> dict:
    """只接受首发支持的确定性条件，拒绝任意脚本或模型表达式。"""

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("策略条件必须是对象")
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in CONDITION_KEYS:
            raise ValueError(f"不支持的策略条件：{key}")
        if key in {
            "allow_high_risk",
            "requires_dual_approval",
        }:
            normalized[key] = bool(value)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"策略条件 {key} 必须是数字") from exc
        if number < 0:
            raise ValueError(f"策略条件 {key} 不能为负数")
        normalized[key] = number
    return normalized


def _load_settings(workspace: Workspace) -> dict:
    try:
        parsed = json.loads(workspace.settings_json or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def workspace_is_paused(workspace: Workspace | None) -> bool:
    return bool(
        workspace is not None
        and _load_settings(workspace).get("agent_paused", False)
    )


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _price_change_percent(input_data: dict) -> Decimal | None:
    explicit = _decimal(input_data.get("change_percent"))
    if explicit is not None:
        return abs(explicit)
    old_price = _decimal(input_data.get("old_price"))
    new_price = _decimal(input_data.get("price"))
    if old_price is None or old_price <= 0 or new_price is None:
        return None
    return abs((new_price - old_price) / old_price * 100)


async def _daily_action_count(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    action_id: str,
) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return int(
        (
            await db.execute(
                select(func.count(ActionRun.id)).where(
                    ActionRun.workspace_id == workspace_id,
                    ActionRun.action_id == action_id,
                    ActionRun.created_at >= since,
                )
            )
        ).scalar()
        or 0
    )


async def _condition_failures(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    definition: "ActionDefinition",
    input_data: dict,
    conditions: dict,
) -> list[str]:
    failures: list[str] = []
    if definition.risk_level == "high" and not conditions.get(
        "allow_high_risk",
        False,
    ):
        failures.append("高风险动作未获自动执行授权")

    max_amount = _decimal(conditions.get("max_amount"))
    if max_amount is not None:
        amount = _decimal(input_data.get("amount"))
        if amount is None or abs(amount) > max_amount:
            failures.append("退款或资金金额超过自动执行上限")

    max_percent = _decimal(conditions.get("max_percent"))
    if max_percent is not None:
        change = _price_change_percent(input_data)
        if change is None or change > max_percent:
            failures.append("价格变化比例超过自动执行上限")

    max_quantity = _decimal(conditions.get("max_quantity"))
    if max_quantity is not None:
        quantity = _decimal(
            input_data.get("stock_quantity")
            if input_data.get("stock_quantity") is not None
            else input_data.get("quantity")
        )
        if quantity is None or abs(quantity) > max_quantity:
            failures.append("库存变更数量超过自动执行上限")

    min_margin = _decimal(conditions.get("min_margin_percent"))
    if min_margin is not None:
        margin = _decimal(input_data.get("margin_percent"))
        if margin is None or margin < min_margin:
            failures.append("毛利低于自动执行下限")

    max_daily = conditions.get("max_daily_actions")
    if max_daily is not None:
        count = await _daily_action_count(
            db,
            workspace_id=workspace_id,
            action_id=definition.action_id,
        )
        if count >= int(max_daily):
            failures.append("最近 24 小时同类动作已达到自动执行上限")
    return failures


async def evaluate_autonomy(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    definition: "ActionDefinition",
    input_data: dict | None = None,
    requested_level: str | None = None,
) -> AutonomyDecision:
    """按工作区策略和实际参数计算本次动作允许的最高自主级别。"""

    if requested_level is not None and requested_level not in AUTONOMY_LEVELS:
        raise ValueError("未知自主级别")
    workspace = await db.get(Workspace, workspace_id)
    paused = workspace_is_paused(workspace)
    policy = (
        await db.execute(
            select(AgentAutonomyPolicy).where(
                AgentAutonomyPolicy.workspace_id == workspace_id,
                AgentAutonomyPolicy.action_id == definition.action_id,
                AgentAutonomyPolicy.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    if policy is None:
        selected = definition.default_autonomy
        conditions: dict = {}
        reasons = ["未配置工作区策略，使用动作默认级别"]
        policy_id = None
        policy_version = None
    else:
        selected = policy.autonomy_level
        try:
            parsed = json.loads(policy.conditions_json or "{}")
        except json.JSONDecodeError:
            parsed = {}
        conditions = normalize_conditions(
            parsed if isinstance(parsed, dict) else {}
        )
        reasons = [f"命中工作区策略 v{policy.version}"]
        policy_id = policy.id
        policy_version = policy.version

    trusted_override = requested_level is not None
    if trusted_override:
        # 该参数只能由服务端受控调用方传入，不能由 LLM 或 App 直接指定。
        selected = requested_level
        reasons.append(f"调用方限制为 {requested_level}")

    if paused and selected == "auto":
        selected = "confirm"
        reasons.append("工作区已暂停 Agent 自动执行")

    if selected == "auto" and not trusted_override:
        failures = await _condition_failures(
            db,
            workspace_id=workspace_id,
            definition=definition,
            input_data=input_data or {},
            conditions=conditions,
        )
        if failures:
            selected = "confirm"
            reasons.extend(failures)

    return AutonomyDecision(
        autonomy_level=selected,
        allowed=True,
        reason="；".join(reasons),
        policy_id=policy_id,
        policy_version=policy_version,
        conditions=conditions,
        paused=paused,
        requires_dual_approval=bool(
            conditions.get("requires_dual_approval", False)
        ),
    )


async def set_agent_paused(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    paused: bool,
) -> tuple[Workspace, int]:
    """切换工作区暂停状态，并冻结尚未执行的自动动作。"""

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("工作区不存在")
    before = _load_settings(workspace)
    settings = {**before, "agent_paused": paused}
    workspace.settings_json = json.dumps(
        settings,
        ensure_ascii=False,
        sort_keys=True,
    )
    db.add(
        WorkspaceAuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action="agent.pause" if paused else "agent.resume",
            resource_type="workspace",
            resource_id=str(workspace_id),
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(settings, ensure_ascii=False),
        )
    )

    frozen = 0
    if paused:
        runs = (
            await db.execute(
                select(ActionRun).where(
                    ActionRun.workspace_id == workspace_id,
                    ActionRun.status == "queued",
                    ActionRun.autonomy_level == "auto",
                )
            )
        ).scalars().all()
        for run in runs:
            item = await db.get(WorkItem, run.work_item_id)
            run.status = "blocked"
            run.error_code = "agent_paused"
            run.verification_json = json.dumps(
                {"error": "工作区已暂停 Agent 自动执行"},
                ensure_ascii=False,
            )
            run.version += 1
            if item is not None and item.workspace_id == workspace_id:
                item.status = "waiting_user"
                item.requires_action = "retry"
                item.current_step = "Agent 已暂停，恢复后可重新排队"
                item.version += 1
                db.add(
                    WorkItemEvent(
                        workspace_id=workspace_id,
                        work_item_id=item.id,
                        event_type="action_run.paused",
                        actor_user_id=actor_user_id,
                        payload_json=json.dumps(
                            {
                                "action_run_id": str(run.id),
                                "action_id": run.action_id,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
            frozen += 1
    await db.flush()
    return workspace, frozen


async def get_workspace_member_role(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> str | None:
    member = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.status == "active",
            )
        )
    ).scalar_one_or_none()
    return member.role if member is not None else None


def decision_requires_dual_approval(run: ActionRun) -> bool:
    try:
        snapshot = json.loads(run.policy_snapshot_json or "{}")
    except json.JSONDecodeError:
        return False
    return bool(
        isinstance(snapshot, dict)
        and snapshot.get("requires_dual_approval")
    )
