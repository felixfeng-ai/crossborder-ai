"""个人工作区账务单一事实源与旧字段兼容镜像。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_wallet import CreditWallet
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.workspaces import ensure_personal_workspace


async def get_personal_workspace(
    db: AsyncSession,
    user: User,
    *,
    workspace_id: UUID | None = None,
) -> Workspace | None:
    """解析本人有效个人工作区；未指定时按需创建。"""

    if workspace_id is not None:
        workspace = await db.get(Workspace, workspace_id)
        if (
            workspace is None
            or workspace.type != "personal"
            or workspace.owner_user_id != user.id
            or workspace.status != "active"
        ):
            raise ValueError("用户钱包只能用于本人有效个人工作区")
        return workspace
    return await ensure_personal_workspace(db, user)


async def get_or_create_personal_wallet(
    db: AsyncSession,
    *,
    user: User,
    workspace: Workspace,
    lock: bool = False,
) -> WorkspaceCreditWallet:
    """读取工作区权威钱包；首次缺失时从旧账本一次性迁移。"""

    query = select(WorkspaceCreditWallet).where(
        WorkspaceCreditWallet.workspace_id == workspace.id
    )
    if lock:
        query = query.with_for_update()
    wallet = (await db.execute(query)).scalar_one_or_none()
    if wallet is not None:
        return wallet

    legacy = await db.get(CreditWallet, user.id)
    if legacy is not None:
        plan_credits = int(legacy.plan_credits or 0)
        purchased_credits = int(legacy.purchased_credits or 0)
    else:
        plan_credits = max(0, int(user.credits or 0))
        purchased_credits = 0
    wallet = WorkspaceCreditWallet(
        workspace_id=workspace.id,
        plan_credits=plan_credits,
        purchased_credits=purchased_credits,
        # 首次创建时只做一次旧周期迁移，此后工作区钱包为权威源。
        credit_period_start=user.credit_period_start,
    )
    db.add(wallet)
    await db.flush()
    if lock:
        return (
            await db.execute(
                select(WorkspaceCreditWallet)
                .where(WorkspaceCreditWallet.workspace_id == workspace.id)
                .with_for_update()
            )
        ).scalar_one()
    return wallet


def workspace_wallet_balance(wallet: WorkspaceCreditWallet) -> int:
    return int(wallet.plan_credits or 0) + int(
        wallet.purchased_credits or 0
    )


async def sync_legacy_wallet_mirror(
    db: AsyncSession,
    *,
    user: User,
    wallet: WorkspaceCreditWallet,
) -> CreditWallet:
    """把工作区权威余额写入旧钱包和 User.credits 兼容字段。"""

    mirror = await db.get(CreditWallet, user.id)
    if mirror is None:
        mirror = CreditWallet(user_id=user.id)
        db.add(mirror)
    mirror.plan_credits = int(wallet.plan_credits or 0)
    mirror.purchased_credits = int(wallet.purchased_credits or 0)
    user.credits = workspace_wallet_balance(wallet)
    period_start = wallet.credit_period_start
    if period_start is not None and period_start.tzinfo is None:
        # SQLite 会丢失时区，返回应用层统一补回 UTC 语义。
        period_start = period_start.replace(tzinfo=timezone.utc)
        wallet.credit_period_start = period_start
    user.credit_period_start = period_start
    await db.flush()
    return mirror


async def get_personal_billing_balance(
    db: AsyncSession,
    user: User,
    *,
    workspace_id: UUID | None = None,
) -> int:
    workspace = await get_personal_workspace(
        db,
        user,
        workspace_id=workspace_id,
    )
    if workspace is None:
        return int(user.credits or 0)
    wallet = await get_or_create_personal_wallet(
        db,
        user=user,
        workspace=workspace,
    )
    return workspace_wallet_balance(wallet)


async def refresh_personal_billing_mirror(
    db: AsyncSession,
    user: User,
) -> None:
    """读取请求前修复旧字段镜像，不创建新的工作区或钱包。"""

    workspace = (
        await db.execute(
            select(Workspace)
            .where(
                Workspace.owner_user_id == user.id,
                Workspace.type == "personal",
                Workspace.status == "active",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if workspace is None:
        return
    wallet = await db.get(WorkspaceCreditWallet, workspace.id)
    if wallet is not None:
        await sync_legacy_wallet_mirror(
            db,
            user=user,
            wallet=wallet,
        )
    subscription = (
        await db.execute(
            select(WorkspaceSubscription)
            .where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
                WorkspaceSubscription.expires_at
                > datetime.now(timezone.utc),
            )
            .order_by(WorkspaceSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if subscription is not None:
        user.plan = subscription.plan
