"""个人用户账务与个人工作区账务对账。"""

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing_reconciliation_case import BillingReconciliationCase
from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription


class BillingSpendingBlockedError(ValueError):
    """个人账务差异未结案时，禁止继续消费积分。"""


class BillingReconciliationRepairError(ValueError):
    """账务差异案件无法按当前数据安全修复。"""


def _bucket() -> dict:
    return {
        "checked": 0,
        "matched": 0,
        "mismatched": 0,
        "repaired": 0,
        "missing_legacy": 0,
    }


def _case_bucket() -> dict:
    return {
        "created": 0,
        "reused": 0,
    }


def _wallet_case_snapshot(
    *,
    legacy_wallet: CreditWallet | None,
    legacy_user: User | None,
    workspace_wallet: WorkspaceCreditWallet | None,
    detected_at: datetime,
) -> str:
    """保存发现时双方余额，审批时仍以最新数据重新计算。"""

    return json.dumps(
        {
            "detected_at": detected_at.isoformat(),
            "legacy": (
                {
                    "plan_credits": legacy_wallet.plan_credits,
                    "purchased_credits": legacy_wallet.purchased_credits,
                    "credit_period_start": (
                        legacy_user.credit_period_start.isoformat()
                        if legacy_user is not None
                        and legacy_user.credit_period_start is not None
                        else None
                    ),
                }
                if legacy_wallet is not None
                else None
            ),
            "workspace": (
                {
                    "plan_credits": workspace_wallet.plan_credits,
                    "purchased_credits": workspace_wallet.purchased_credits,
                    "credit_period_start": (
                        workspace_wallet.credit_period_start.isoformat()
                        if workspace_wallet.credit_period_start is not None
                        else None
                    ),
                }
                if workspace_wallet is not None
                else None
            ),
        },
        ensure_ascii=False,
    )


async def _mirror_workspace_wallet_to_legacy(
    db: AsyncSession,
    *,
    owner_id: UUID,
    workspace_wallet: WorkspaceCreditWallet,
    legacy_wallet: CreditWallet | None,
) -> CreditWallet:
    """以工作区权威余额修复旧钱包与 User.credits 镜像。"""

    if legacy_wallet is None:
        legacy_wallet = CreditWallet(user_id=owner_id)
        db.add(legacy_wallet)
    legacy_wallet.plan_credits = int(workspace_wallet.plan_credits or 0)
    legacy_wallet.purchased_credits = int(
        workspace_wallet.purchased_credits or 0
    )
    owner = await db.get(User, owner_id)
    if owner is not None:
        owner.credits = (
            legacy_wallet.plan_credits
            + legacy_wallet.purchased_credits
        )
        period_start = workspace_wallet.credit_period_start
        if period_start is not None and period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)
            workspace_wallet.credit_period_start = period_start
        owner.credit_period_start = period_start
    await db.flush()
    return legacy_wallet


async def _record_wallet_case(
    db: AsyncSession,
    *,
    cases: dict,
    workspace: Workspace,
    legacy_wallet: CreditWallet | None,
    legacy_user: User | None,
    workspace_wallet: WorkspaceCreditWallet | None,
    detected_at: datetime,
) -> None:
    """同一工作区只保留一个未结案，重复对账刷新差异快照。"""

    existing = (
        await db.execute(
            select(BillingReconciliationCase)
            .where(
                BillingReconciliationCase.workspace_id == workspace.id,
                BillingReconciliationCase.status == "open",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    snapshot_json = _wallet_case_snapshot(
        legacy_wallet=legacy_wallet,
        legacy_user=legacy_user,
        workspace_wallet=workspace_wallet,
        detected_at=detected_at,
    )
    if existing is not None:
        existing.snapshot_json = snapshot_json
        existing.version += 1
        cases["reused"] += 1
        return

    db.add(
        BillingReconciliationCase(
            workspace_id=workspace.id,
            status="open",
            snapshot_json=snapshot_json,
        )
    )
    cases["created"] += 1


async def assert_personal_billing_spending_allowed(
    db: AsyncSession,
    *,
    workspace_id: UUID,
) -> None:
    """检查个人工作区是否存在未审批的账务差异案件。"""

    case_id = (
        await db.execute(
            select(BillingReconciliationCase.id)
            .where(
                BillingReconciliationCase.workspace_id == workspace_id,
                BillingReconciliationCase.status == "open",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if case_id is not None:
        raise BillingSpendingBlockedError(
            f"账务差异待人工修复，已暂停积分消费（案件 {case_id}）"
        )


def billing_reconciliation_case_response(
    case: BillingReconciliationCase,
) -> dict:
    """把案件转为管理端可审计响应，解析失败时保留原始快照。"""

    try:
        snapshot = json.loads(case.snapshot_json or "{}")
    except json.JSONDecodeError:
        snapshot = {"raw": case.snapshot_json}
    return {
        "id": str(case.id),
        "workspace_id": str(case.workspace_id),
        "status": case.status,
        "snapshot": snapshot,
        "note": case.note,
        "approved_by_user_id": (
            str(case.approved_by_user_id)
            if case.approved_by_user_id
            else None
        ),
        "approved_at": (
            case.approved_at.isoformat() if case.approved_at else None
        ),
        "resolved_at": (
            case.resolved_at.isoformat() if case.resolved_at else None
        ),
        "version": case.version,
        "created_at": (
            case.created_at.isoformat() if case.created_at else None
        ),
    }


async def approve_billing_reconciliation_case(
    db: AsyncSession,
    *,
    case_id: UUID,
    approved_by_user_id: UUID,
    note: str = "",
    now: datetime | None = None,
) -> dict:
    """管理员批准后重新核对目标工作区，并只修复当前案件对应钱包。"""

    case = (
        await db.execute(
            select(BillingReconciliationCase)
            .where(BillingReconciliationCase.id == case_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if case is None:
        raise BillingReconciliationRepairError("账务差异案件不存在")
    if case.status == "resolved":
        return {
            "case": billing_reconciliation_case_response(case),
            "repaired": False,
            "already_resolved": True,
        }

    workspace = await db.get(Workspace, case.workspace_id)
    if (
        workspace is None
        or workspace.type != "personal"
        or workspace.status != "active"
    ):
        raise BillingReconciliationRepairError(
            "案件工作区不存在或不是有效个人工作区"
        )

    legacy_wallet = (
        await db.execute(
            select(CreditWallet).where(
                CreditWallet.user_id == workspace.owner_user_id
            )
        )
    ).scalar_one_or_none()
    workspace_wallet = await db.get(WorkspaceCreditWallet, workspace.id)
    owner = await db.get(User, workspace.owner_user_id)
    if workspace_wallet is None and legacy_wallet is not None:
        workspace_wallet = WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=legacy_wallet.plan_credits,
            purchased_credits=legacy_wallet.purchased_credits,
            credit_period_start=(
                owner.credit_period_start if owner is not None else None
            ),
        )
        db.add(workspace_wallet)
        repaired = True
    elif workspace_wallet is None:
        raise BillingReconciliationRepairError(
            "旧用户钱包和工作区钱包均缺失"
        )
    else:
        repaired = (
            legacy_wallet is None
            or workspace_wallet.plan_credits != legacy_wallet.plan_credits
            or workspace_wallet.purchased_credits
            != legacy_wallet.purchased_credits
            or not _same_optional_datetime(
                owner.credit_period_start if owner is not None else None,
                workspace_wallet.credit_period_start,
            )
        )
    if repaired:
        if legacy_wallet is not None or workspace_wallet is not None:
            legacy_wallet = await _mirror_workspace_wallet_to_legacy(
                db,
                owner_id=workspace.owner_user_id,
                workspace_wallet=workspace_wallet,
                legacy_wallet=legacy_wallet,
            )

    current = now or datetime.now(timezone.utc)
    case.status = "resolved"
    case.note = note[:500]
    case.approved_by_user_id = approved_by_user_id
    case.approved_at = current
    case.resolved_at = current
    case.version += 1
    await db.flush()
    return {
        "case": billing_reconciliation_case_response(case),
        "repaired": repaired,
        "already_resolved": False,
        "wallet": {
            "plan_credits": (
                workspace_wallet.plan_credits
                if workspace_wallet is not None
                else 0
            ),
            "purchased_credits": (
                workspace_wallet.purchased_credits
                if workspace_wallet is not None
                else 0
            ),
        },
    }


def _same_datetime(left: datetime, right: datetime) -> bool:
    """统一时区后比较时间，兼容 SQLite 的朴素时间。"""

    def normalize(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )

    return normalize(left) == normalize(right)


def _same_optional_datetime(
    left: datetime | None,
    right: datetime | None,
) -> bool:
    """比较可空时间，周期同时为空时视为一致。"""

    if left is None or right is None:
        return left is None and right is None
    return _same_datetime(left, right)


def _subscription_matches(
    legacy: UserSubscription,
    workspace: WorkspaceSubscription,
) -> bool:
    return (
        workspace.plan == legacy.plan
        and _same_datetime(workspace.starts_at, legacy.starts_at)
        and _same_datetime(workspace.expires_at, legacy.expires_at)
    )


async def _ledger_summary(
    db: AsyncSession,
    *,
    owner_ids: set[UUID],
    workspace_ids: set[UUID],
) -> dict:
    """汇总个人账本；已归属流水只算一次，未归属流水独立核对。"""

    if not owner_ids:
        return {
            "legacy_wallet_count": 0,
            "workspace_wallet_count": 0,
            "legacy_transaction_count": 0,
            "workspace_transaction_count": 0,
            "unassigned_transaction_count": 0,
            "legacy_delta": 0,
            "workspace_delta": 0,
            "unassigned_delta": 0,
            "legacy_plan_credits": 0,
            "legacy_purchased_credits": 0,
            "legacy_total_credits": 0,
            "workspace_plan_credits": 0,
            "workspace_purchased_credits": 0,
            "workspace_total_credits": 0,
            "plan_credit_delta": 0,
            "purchased_credit_delta": 0,
            "total_credit_delta": 0,
            "wallet_count_delta": 0,
            "requires_attention": False,
        }

    # 旧用户视角按 user_id 覆盖其全部流水，包括团队工作区中的操作。
    # workspace_id 与 user_id 同时存在于同一行，因此已归属统计是其子集。
    ledger_scope = CreditTransaction.user_id.in_(owner_ids)
    assigned = CreditTransaction.workspace_id.is_not(None)
    unassigned = CreditTransaction.workspace_id.is_(None)
    transaction_row = (
        await db.execute(
            select(
                func.count(CreditTransaction.id),
                func.coalesce(func.sum(CreditTransaction.delta), 0),
                func.coalesce(
                    func.sum(case((assigned, 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (assigned, CreditTransaction.delta),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(case((unassigned, 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (unassigned, CreditTransaction.delta),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(ledger_scope)
        )
    ).one()

    legacy_wallet_row = (
        await db.execute(
            select(
                func.count(CreditWallet.user_id),
                func.coalesce(func.sum(CreditWallet.plan_credits), 0),
                func.coalesce(func.sum(CreditWallet.purchased_credits), 0),
            ).where(CreditWallet.user_id.in_(owner_ids))
        )
    ).one()
    workspace_wallet_row = (
        await db.execute(
            select(
                func.count(WorkspaceCreditWallet.workspace_id),
                func.coalesce(
                    func.sum(WorkspaceCreditWallet.plan_credits),
                    0,
                ),
                func.coalesce(
                    func.sum(WorkspaceCreditWallet.purchased_credits),
                    0,
                ),
            ).where(WorkspaceCreditWallet.workspace_id.in_(workspace_ids))
        )
    ).one()

    legacy_wallet_count = int(legacy_wallet_row[0] or 0)
    workspace_wallet_count = int(workspace_wallet_row[0] or 0)
    legacy_plan_credits = int(legacy_wallet_row[1] or 0)
    legacy_purchased_credits = int(legacy_wallet_row[2] or 0)
    workspace_plan_credits = int(workspace_wallet_row[1] or 0)
    workspace_purchased_credits = int(workspace_wallet_row[2] or 0)
    legacy_total_credits = legacy_plan_credits + legacy_purchased_credits
    workspace_total_credits = (
        workspace_plan_credits + workspace_purchased_credits
    )
    plan_credit_delta = legacy_plan_credits - workspace_plan_credits
    purchased_credit_delta = (
        legacy_purchased_credits - workspace_purchased_credits
    )
    total_credit_delta = legacy_total_credits - workspace_total_credits
    unassigned_transaction_count = int(transaction_row[4] or 0)
    unassigned_delta = int(transaction_row[5] or 0)
    wallet_count_delta = legacy_wallet_count - workspace_wallet_count

    requires_attention = any(
        (
            unassigned_transaction_count,
            unassigned_delta,
            plan_credit_delta,
            purchased_credit_delta,
            wallet_count_delta,
        )
    )
    return {
        "legacy_wallet_count": legacy_wallet_count,
        "workspace_wallet_count": workspace_wallet_count,
        "legacy_transaction_count": int(transaction_row[0] or 0),
        "workspace_transaction_count": int(transaction_row[2] or 0),
        "unassigned_transaction_count": unassigned_transaction_count,
        "legacy_delta": int(transaction_row[1] or 0),
        "workspace_delta": int(transaction_row[3] or 0),
        "unassigned_delta": unassigned_delta,
        "legacy_plan_credits": legacy_plan_credits,
        "legacy_purchased_credits": legacy_purchased_credits,
        "legacy_total_credits": legacy_total_credits,
        "workspace_plan_credits": workspace_plan_credits,
        "workspace_purchased_credits": workspace_purchased_credits,
        "workspace_total_credits": workspace_total_credits,
        "plan_credit_delta": plan_credit_delta,
        "purchased_credit_delta": purchased_credit_delta,
        "total_credit_delta": total_credit_delta,
        "wallet_count_delta": wallet_count_delta,
        "requires_attention": requires_attention,
    }


async def _repair_subscription(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    owner_id: UUID,
    legacy: UserSubscription | None,
) -> None:
    """显式修复时以用户订阅为准更新个人工作区订阅。"""

    active = (
        await db.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace_id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalars().all()
    if legacy is None:
        for item in active:
            item.status = "expired"
        return

    matching = next(
        (item for item in active if item.plan == legacy.plan),
        None,
    )
    for item in active:
        if item is not matching:
            item.status = "replaced"
    if matching is None:
        db.add(
            WorkspaceSubscription(
                workspace_id=workspace_id,
                plan=legacy.plan,
                status="active",
                starts_at=legacy.starts_at,
                expires_at=legacy.expires_at,
                payer_user_id=owner_id,
                source=legacy.source,
            )
        )
    else:
        matching.starts_at = legacy.starts_at
        matching.expires_at = legacy.expires_at
        matching.payer_user_id = owner_id
        matching.source = legacy.source


async def reconcile_personal_workspace_billing(
    db: AsyncSession,
    *,
    batch_size: int = 500,
    repair: bool = False,
    record_cases: bool = False,
    now: datetime | None = None,
) -> dict:
    """对账默认只报告；记录案件和显式修复必须分别启用。"""

    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    if repair and record_cases:
        raise ValueError("修复与案件记录不能在同一轮执行")
    current = now or datetime.now(timezone.utc)
    wallets = _bucket()
    subscriptions = _bucket()
    cases = _case_bucket()
    mismatch_samples: list[dict] = []
    checked = 0
    cursor: UUID | None = None
    owner_ids: set[UUID] = set()
    personal_workspace_ids: set[UUID] = set()

    while True:
        query = (
            select(Workspace)
            .where(
                Workspace.type == "personal",
                Workspace.status == "active",
            )
            .order_by(Workspace.id)
            .limit(batch_size)
        )
        if cursor is not None:
            query = query.where(Workspace.id > cursor)
        workspaces = (await db.execute(query)).scalars().all()
        if not workspaces:
            break
        checked += len(workspaces)
        cursor = workspaces[-1].id
        owner_ids.update(workspace.owner_user_id for workspace in workspaces)
        personal_workspace_ids.update(workspace.id for workspace in workspaces)

        for workspace in workspaces:
            owner_id = workspace.owner_user_id
            owner = (
                await db.get(User, owner_id)
                if owner_id is not None
                else None
            )
            wallet_pair = (wallets, subscriptions)
            wallet_pair[0]["checked"] += 1
            wallet_pair[1]["checked"] += 1
            legacy_wallet = (
                await db.execute(
                    select(CreditWallet).where(
                        CreditWallet.user_id == owner_id
                    )
                )
            ).scalar_one_or_none()
            workspace_wallet = await db.get(
                WorkspaceCreditWallet,
                workspace.id,
            )
            wallet_mismatch = False
            if legacy_wallet is None:
                wallets["missing_legacy"] += 1
                wallet_mismatch = workspace_wallet is not None
            elif workspace_wallet is None or (
                workspace_wallet.plan_credits
                != legacy_wallet.plan_credits
                or workspace_wallet.purchased_credits
                != legacy_wallet.purchased_credits
                or not _same_optional_datetime(
                    owner.credit_period_start if owner is not None else None,
                    workspace_wallet.credit_period_start,
                )
            ):
                wallet_mismatch = True

            if wallet_mismatch:
                wallets["mismatched"] += 1
                if record_cases:
                    await _record_wallet_case(
                        db,
                        cases=cases,
                        workspace=workspace,
                        legacy_wallet=legacy_wallet,
                        legacy_user=owner,
                        workspace_wallet=workspace_wallet,
                        detected_at=current,
                    )
                if repair:
                    if workspace_wallet is None and legacy_wallet is not None:
                        workspace_wallet = WorkspaceCreditWallet(
                            workspace_id=workspace.id,
                            plan_credits=legacy_wallet.plan_credits,
                            purchased_credits=legacy_wallet.purchased_credits,
                            credit_period_start=(
                                owner.credit_period_start
                                if owner is not None
                                else None
                            ),
                        )
                        db.add(workspace_wallet)
                    if workspace_wallet is not None:
                        legacy_wallet = (
                            await _mirror_workspace_wallet_to_legacy(
                                db,
                                owner_id=owner_id,
                                workspace_wallet=workspace_wallet,
                                legacy_wallet=legacy_wallet,
                            )
                        )
                        wallets["repaired"] += 1
            else:
                wallets["matched"] += 1

            legacy_subscription = (
                await db.execute(
                    select(UserSubscription)
                    .where(
                        UserSubscription.user_id == owner_id,
                        UserSubscription.status == "active",
                        UserSubscription.expires_at > current,
                    )
                    .order_by(UserSubscription.expires_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            workspace_subscription = (
                await db.execute(
                    select(WorkspaceSubscription)
                    .where(
                        WorkspaceSubscription.workspace_id == workspace.id,
                        WorkspaceSubscription.status == "active",
                        WorkspaceSubscription.expires_at > current,
                    )
                    .order_by(WorkspaceSubscription.expires_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            subscription_mismatch = (
                (legacy_subscription is None)
                != (workspace_subscription is None)
            )
            if legacy_subscription and workspace_subscription:
                subscription_mismatch = not _subscription_matches(
                    legacy_subscription,
                    workspace_subscription,
                )

            if subscription_mismatch:
                subscriptions["mismatched"] += 1
                if repair:
                    await _repair_subscription(
                        db,
                        workspace_id=workspace.id,
                        owner_id=owner_id,
                        legacy=legacy_subscription,
                    )
                    subscriptions["repaired"] += 1
            else:
                subscriptions["matched"] += 1

            if wallet_mismatch or subscription_mismatch:
                if len(mismatch_samples) < 20:
                    mismatch_samples.append(
                        {
                            "workspace_id": str(workspace.id),
                            "wallet": wallet_mismatch,
                            "subscription": subscription_mismatch,
                        }
                    )

        if repair or record_cases:
            await db.flush()

    ledger = await _ledger_summary(
        db,
        owner_ids=owner_ids,
        workspace_ids=personal_workspace_ids,
    )
    return {
        "workspaces_checked": checked,
        "repair": repair,
        "wallets": wallets,
        "subscriptions": subscriptions,
        "cases": cases,
        "ledger": ledger,
        "summary": {
            "workspace_count": checked,
            "wallet_matches": wallets["matched"],
            "wallet_mismatches": wallets["mismatched"],
            "wallet_repaired": wallets["repaired"],
            "subscription_matches": subscriptions["matched"],
            "subscription_mismatches": subscriptions["mismatched"],
            "subscription_repaired": subscriptions["repaired"],
            "cases_created": cases["created"],
            "cases_reused": cases["reused"],
            "unassigned_transaction_count": ledger[
                "unassigned_transaction_count"
            ],
            "unassigned_delta": ledger["unassigned_delta"],
            "ledger_requires_attention": ledger["requires_attention"],
        },
        "mismatch_samples": mismatch_samples,
    }
