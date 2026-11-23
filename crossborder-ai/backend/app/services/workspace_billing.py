"""团队工作区积分钱包与扣费。"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.models.user import InsufficientCreditsError
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.plan_catalog_service import get_effective_plan_config
from app.services.plan_defaults import PLAN_CATALOG


async def get_or_create_workspace_wallet(
    db: AsyncSession,
    workspace: Workspace,
    *,
    lock: bool = False,
) -> WorkspaceCreditWallet:
    query = select(WorkspaceCreditWallet).where(
        WorkspaceCreditWallet.workspace_id == workspace.id
    )
    if lock:
        query = query.with_for_update()
    wallet = (await db.execute(query)).scalar_one_or_none()
    if wallet is not None:
        return wallet

    dialect = db.get_bind().dialect.name
    values = {
        "workspace_id": workspace.id,
        "plan_credits": 0,
        "purchased_credits": 0,
    }
    if dialect == "postgresql":
        statement = (
            postgresql_insert(WorkspaceCreditWallet)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["workspace_id"])
        )
    elif dialect == "sqlite":
        statement = (
            sqlite_insert(WorkspaceCreditWallet)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["workspace_id"])
        )
    else:
        statement = insert(WorkspaceCreditWallet).values(**values)
    await db.execute(statement)
    await db.flush()
    query = select(WorkspaceCreditWallet).where(
        WorkspaceCreditWallet.workspace_id == workspace.id
    )
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one()


def workspace_wallet_total(wallet: WorkspaceCreditWallet) -> int:
    return int(wallet.plan_credits or 0) + int(wallet.purchased_credits or 0)


async def deduct_workspace_credits(
    db: AsyncSession,
    *,
    workspace: Workspace,
    actor_user_id: UUID,
    amount: int,
    feature: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    description: str = "",
) -> int:
    if workspace.type == "personal":
        from app.models.user import User

        user = await db.get(User, actor_user_id)
        if user is None or workspace.owner_user_id != user.id:
            raise ValueError("个人工作区扣费用户无效")
        return await user.deduct_credits(
            db,
            amount,
            workspace_id=workspace.id,
            actor_user_id=actor_user_id,
            feature=feature,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    if amount <= 0:
        return workspace_wallet_total(
            await get_or_create_workspace_wallet(db, workspace, lock=True)
        )

    wallet = await get_or_create_workspace_wallet(db, workspace, lock=True)
    available = workspace_wallet_total(wallet)
    if available < amount:
        raise InsufficientCreditsError(
            f"积分不足，需要 {amount}，当前 {available}"
        )

    plan_spend = min(int(wallet.plan_credits or 0), amount)
    purchased_spend = amount - plan_spend
    wallet.plan_credits -= plan_spend
    wallet.purchased_credits -= purchased_spend
    balance_after = workspace_wallet_total(wallet)
    wallet_type = (
        "plan"
        if purchased_spend == 0
        else "purchased"
        if plan_spend == 0
        else "mixed"
    )
    db.add(
        CreditTransaction(
            user_id=actor_user_id,
            workspace_id=workspace.id,
            actor_user_id=actor_user_id,
            delta=-amount,
            balance_after=balance_after,
            feature=feature,
            wallet_type=wallet_type,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description or f"扣减 {amount} 积分",
        )
    )
    await db.flush()
    return balance_after


async def get_workspace_credit_balance(
    db: AsyncSession,
    workspace: Workspace,
) -> int:
    wallet = await get_or_create_workspace_wallet(db, workspace)
    return workspace_wallet_total(wallet)


async def grant_workspace_purchased_credits(
    db: AsyncSession,
    *,
    workspace: Workspace,
    actor_user_id: UUID,
    amount: int,
    reference_type: str,
    reference_id: str,
) -> int:
    if amount <= 0:
        return 0
    existing = (
        await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.workspace_id == workspace.id,
                CreditTransaction.wallet_type == "purchased",
                CreditTransaction.reference_type == reference_type,
                CreditTransaction.reference_id == reference_id,
                CreditTransaction.feature == "credit_pack_purchase",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return 0

    wallet = await get_or_create_workspace_wallet(db, workspace, lock=True)
    wallet.purchased_credits += amount
    db.add(
        CreditTransaction(
            user_id=actor_user_id,
            workspace_id=workspace.id,
            actor_user_id=actor_user_id,
            delta=amount,
            balance_after=workspace_wallet_total(wallet),
            feature="credit_pack_purchase",
            wallet_type="purchased",
            reference_type=reference_type,
            reference_id=reference_id,
            description="积分包到账",
        )
    )
    await db.flush()
    return amount


def workspace_wallet_response(
    workspace: Workspace,
    wallet: WorkspaceCreditWallet,
    subscription: WorkspaceSubscription | None = None,
) -> dict:
    return {
        "workspace_id": str(workspace.id),
        "plan": subscription.plan if subscription else "free",
        "plan_credits": wallet.plan_credits,
        "purchased_credits": wallet.purchased_credits,
        "total_credits": workspace_wallet_total(wallet),
        "credit_period_start": (
            str(wallet.credit_period_start)
            if wallet.credit_period_start
            else None
        ),
        "plan_expires_at": (
            str(subscription.expires_at) if subscription else None
        ),
        "subscription_status": (
            subscription.status if subscription else "free"
        ),
    }


async def get_active_workspace_subscription(
    db: AsyncSession,
    workspace_id: UUID,
    *,
    now: datetime | None = None,
) -> WorkspaceSubscription | None:
    current = now or datetime.now(timezone.utc)
    return (
        await db.execute(
            select(WorkspaceSubscription)
            .where(
                WorkspaceSubscription.workspace_id == workspace_id,
                WorkspaceSubscription.status == "active",
                WorkspaceSubscription.expires_at > current,
            )
            .order_by(WorkspaceSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_workspace_current_plan(
    db: AsyncSession,
    workspace_id: UUID,
) -> str:
    subscription = await get_active_workspace_subscription(
        db,
        workspace_id,
    )
    return subscription.plan if subscription else "free"


async def activate_workspace_plan(
    db: AsyncSession,
    *,
    workspace: Workspace,
    plan: str,
    payer_user_id: UUID,
    duration_days: int | None = None,
    now: datetime | None = None,
    source: str = "manual_transfer",
) -> WorkspaceSubscription:
    plan_config = (
        await get_effective_plan_config(db, plan)
        or PLAN_CATALOG.get(plan)
    )
    if not plan_config or plan == "free":
        raise ValueError("无效的付费套餐")
    current = now or datetime.now(timezone.utc)

    active = (
        await db.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalars().all()
    for subscription in active:
        subscription.status = "replaced"

    subscription = WorkspaceSubscription(
        workspace_id=workspace.id,
        plan=plan,
        status="active",
        starts_at=current,
        expires_at=current + timedelta(
            days=duration_days or int(plan_config["valid_days"])
        ),
        payer_user_id=payer_user_id,
        source=source,
    )
    db.add(subscription)

    wallet = await get_or_create_workspace_wallet(
        db,
        workspace,
        lock=True,
    )
    wallet.plan_credits = int(plan_config["monthly_credits"])
    await db.flush()
    return subscription
