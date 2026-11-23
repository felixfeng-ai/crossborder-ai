"""套餐、双钱包、有效期和功能免费额度。"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.feature_usage import FeatureUsageCounter
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.plan_catalog_service import get_effective_plan_config
from app.services.plan_defaults import PLAN_CATALOG
from app.services.personal_billing import (
    get_or_create_personal_wallet,
    get_personal_workspace,
    sync_legacy_wallet_mirror,
    workspace_wallet_balance,
)
from app.services.workspaces import ensure_personal_workspace
from app.services.workspace_billing import activate_workspace_plan


ANALYSIS_LIMITS = {
    "category_analysis": 10,
    "ai_insights": 10,
}

MANUAL_STORE_CHECK_LIMITS = {
    "free": 0,
    "standard": 10,
    "professional": 20,
}

PRODUCT_SCRAPE_LIMITS = {
    "free": 10,
    "standard": 100,
    "professional": 300,
}


async def _personal_workspace_for_user(
    db: AsyncSession,
    user: User,
) -> Workspace | None:
    """读取用户个人工作区，用于同步旧用户账务。"""

    return (
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


async def _sync_legacy_subscription(
    db: AsyncSession,
    *,
    user: User,
    workspace_subscription: WorkspaceSubscription,
) -> UserSubscription:
    """把工作区订阅写入旧订阅表和 User.plan 兼容镜像。"""

    active = (
        await db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
            )
        )
    ).scalars().all()
    matching = next(
        (item for item in active if item.plan == workspace_subscription.plan),
        None,
    )
    for item in active:
        if item is not matching:
            item.status = "replaced"
    if matching is None:
        matching = UserSubscription(
            user_id=user.id,
            plan=workspace_subscription.plan,
            status="active",
            starts_at=workspace_subscription.starts_at,
            expires_at=workspace_subscription.expires_at,
            source=workspace_subscription.source,
        )
        db.add(matching)
    else:
        matching.starts_at = workspace_subscription.starts_at
        matching.expires_at = workspace_subscription.expires_at
        matching.source = workspace_subscription.source
    user.plan = workspace_subscription.plan
    await db.flush()
    return matching


async def _ensure_workspace_subscription(
    db: AsyncSession,
    *,
    user: User,
    workspace: Workspace | None,
    now: datetime,
) -> tuple[WorkspaceSubscription | None, bool]:
    """从旧订阅一次性导入工作区；之后工作区订阅为权威。"""

    if workspace is None:
        return None, False
    workspace_subscription = (
        await db.execute(
            select(WorkspaceSubscription)
            .where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
                WorkspaceSubscription.expires_at > now,
            )
            .order_by(WorkspaceSubscription.expires_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if workspace_subscription is not None:
        await _sync_legacy_subscription(
            db,
            user=user,
            workspace_subscription=workspace_subscription,
        )
        return workspace_subscription, False

    legacy = (
        await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > now,
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    plan = legacy.plan if legacy is not None else user.plan
    if plan not in {"standard", "professional"}:
        return None, False
    plan_config = (
        await get_effective_plan_config(db, plan)
        or PLAN_CATALOG.get(plan, PLAN_CATALOG["free"])
    )
    workspace_subscription = WorkspaceSubscription(
        workspace_id=workspace.id,
        plan=plan,
        status="active",
        starts_at=(
            legacy.starts_at
            if legacy is not None
            else now
        ),
        expires_at=(
            legacy.expires_at
            if legacy is not None
            else now + timedelta(days=plan_config["valid_days"])
        ),
        payer_user_id=user.id,
        source=(
            legacy.source
            if legacy is not None
            else "automatic_plan_reconciliation"
        ),
    )
    db.add(workspace_subscription)
    await db.flush()
    await _sync_legacy_subscription(
        db,
        user=user,
        workspace_subscription=workspace_subscription,
    )
    # 只有缺失任何历史订阅、由 user.plan 自动补建时才需要立即补额度。
    return workspace_subscription, legacy is None


async def get_or_create_wallet(
    db: AsyncSession,
    user: User,
    *,
    lock: bool = False,
) -> CreditWallet:
    workspace = await get_personal_workspace(db, user)
    if workspace is None:
        raise ValueError("个人工作区不存在")
    workspace_wallet = await get_or_create_personal_wallet(
        db,
        user=user,
        workspace=workspace,
        lock=lock,
    )
    return await sync_legacy_wallet_mirror(
        db,
        user=user,
        wallet=workspace_wallet,
    )


def wallet_total(wallet: CreditWallet) -> int:
    return int(wallet.plan_credits or 0) + int(wallet.purchased_credits or 0)


async def _reclassify_excess_plan_credits(
    db: AsyncSession,
    user: User,
    wallet: WorkspaceCreditWallet,
    allowance: int,
    workspace: Workspace | None = None,
) -> CreditTransaction | None:
    """历史积分超出当前套餐额度时转成购买积分，保证总额不丢失。"""
    if user.plan not in {"standard", "professional"}:
        return None
    excess = int(wallet.plan_credits or 0) - allowance
    if excess <= 0:
        return None
    wallet.plan_credits = allowance
    wallet.purchased_credits = int(wallet.purchased_credits or 0) + excess
    await sync_legacy_wallet_mirror(
        db,
        user=user,
        wallet=wallet,
    )
    transaction = CreditTransaction(
        user_id=user.id,
        workspace_id=workspace.id if workspace else None,
        actor_user_id=user.id,
        delta=0,
        balance_after=workspace_wallet_balance(wallet),
        wallet_type="purchased",
        feature="legacy_plan_credit_reclassification",
        reference_type="plan",
        reference_id=user.plan,
        description="历史套餐积分超出月度额度，差额转为购买积分",
        metadata_json=json.dumps(
            {
                "plan": user.plan,
                "plan_allowance": allowance,
                "reclassified_credits": excess,
            },
            ensure_ascii=False,
        ),
    )
    db.add(transaction)
    await db.flush()
    return transaction


async def apply_monthly_allowance(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> CreditTransaction | None:
    current = now or datetime.now(timezone.utc)
    # 同一用户可能同时请求 /auth/me 和 /billing/wallet；锁住用户行避免
    # 两个请求同时创建订阅或重复发放月度额度。
    locked_user = (
        await db.execute(
            select(User).where(User.id == user.id).with_for_update()
        )
    ).scalar_one()
    user = locked_user
    personal_workspace = await get_personal_workspace(db, user)
    workspace_subscription, reconciled = await _ensure_workspace_subscription(
        db,
        user=user,
        workspace=personal_workspace,
        now=current,
    )
    effective_plan = (
        workspace_subscription.plan
        if workspace_subscription is not None
        else user.plan
    )
    user.plan = effective_plan
    wallet = await get_or_create_personal_wallet(
        db,
        user=user,
        workspace=personal_workspace,
        lock=True,
    )

    # 额度周期只认工作区钱包；旧用户字段仅作为兼容镜像。
    same_period = bool(
        wallet.credit_period_start
        and wallet.credit_period_start.year == current.year
        and wallet.credit_period_start.month == current.month
    )
    if not force and same_period and not reconciled:
        plan_config = (
            await get_effective_plan_config(db, effective_plan)
            or PLAN_CATALOG.get(effective_plan, PLAN_CATALOG["free"])
        )
        allowance = int(plan_config["monthly_credits"])
        result = await _reclassify_excess_plan_credits(
            db,
            user,
            wallet,
            allowance,
            personal_workspace,
        )
        await sync_legacy_wallet_mirror(
            db,
            user=user,
            wallet=wallet,
        )
        return result

    plan_config = (
        await get_effective_plan_config(db, effective_plan)
        or PLAN_CATALOG.get(effective_plan, PLAN_CATALOG["free"])
    )
    allowance = int(plan_config["monthly_credits"])
    await _reclassify_excess_plan_credits(
        db,
        user,
        wallet,
        allowance,
        personal_workspace,
    )
    previous_total = workspace_wallet_balance(wallet)
    wallet.plan_credits = allowance
    wallet.credit_period_start = current
    await sync_legacy_wallet_mirror(
        db,
        user=user,
        wallet=wallet,
    )

    transaction = CreditTransaction(
        user_id=user.id,
        workspace_id=(
            personal_workspace.id if personal_workspace else None
        ),
        actor_user_id=user.id,
        delta=workspace_wallet_balance(wallet) - previous_total,
        balance_after=workspace_wallet_balance(wallet),
        wallet_type="plan",
        feature="monthly_allowance",
        reference_type="plan",
        reference_id=effective_plan,
        description=f"{effective_plan} 套餐 {current:%Y-%m} 月度额度",
        metadata_json=json.dumps(
            {
                "plan": effective_plan,
                "allowance": allowance,
                "purchased_credits": wallet.purchased_credits,
                "period": current.strftime("%Y-%m"),
            },
            ensure_ascii=False,
        ),
    )
    db.add(transaction)
    await db.flush()
    return transaction


async def add_purchased_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    *,
    feature: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    description: str = "",
) -> int:
    if amount <= 0:
        return user.credits
    workspace = await ensure_personal_workspace(db, user)
    wallet = await get_or_create_personal_wallet(
        db,
        user=user,
        workspace=workspace,
        lock=True,
    )
    wallet.purchased_credits += amount
    mirror = await sync_legacy_wallet_mirror(
        db,
        user=user,
        wallet=wallet,
    )
    db.add(
        CreditTransaction(
            user_id=user.id,
            workspace_id=workspace.id,
            actor_user_id=user.id,
            delta=amount,
            balance_after=mirror.plan_credits + mirror.purchased_credits,
            wallet_type="purchased",
            feature=feature,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description or f"增加 {amount} 积分",
        )
    )
    await db.flush()
    return workspace_wallet_balance(wallet)


async def grant_purchased_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    *,
    reference_type: str,
    reference_id: str,
) -> int:
    existing = (
        await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.wallet_type == "purchased",
                CreditTransaction.reference_type == reference_type,
                CreditTransaction.reference_id == reference_id,
                CreditTransaction.feature == "credit_pack_purchase",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return 0
    await add_purchased_credits(
        db,
        user,
        amount,
        feature="credit_pack_purchase",
        reference_type=reference_type,
        reference_id=reference_id,
        description="积分包到账",
    )
    return amount


async def activate_paid_plan(
    db: AsyncSession,
    user: User,
    plan: str,
    *,
    now: datetime | None = None,
    source: str = "manual_transfer",
    duration_days: int | None = None,
) -> UserSubscription:
    settings = await get_effective_plan_config(db, plan)
    if not settings or plan == "free":
        raise ValueError("无效的付费套餐")
    current = now or datetime.now(timezone.utc)
    workspace = await get_personal_workspace(db, user)
    workspace_wallet = await get_or_create_personal_wallet(
        db,
        user=user,
        workspace=workspace,
        lock=True,
    )
    workspace_subscription = await activate_workspace_plan(
        db,
        workspace=workspace,
        plan=plan,
        payer_user_id=user.id,
        duration_days=duration_days,
        now=current,
        source=source,
    )
    user.plan = plan
    # 套餐开通即进入新额度周期；清空周期会导致下一次余额读取重复补发额度。
    workspace_wallet.credit_period_start = current
    subscription = await _sync_legacy_subscription(
        db,
        user=user,
        workspace_subscription=workspace_subscription,
    )
    await sync_legacy_wallet_mirror(
        db,
        user=user,
        wallet=workspace_wallet,
    )
    await db.flush()
    return subscription


async def expire_due_subscriptions(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(timezone.utc)
    workspace_rows = (
        await db.execute(
            select(WorkspaceSubscription, Workspace)
            .join(Workspace, Workspace.id == WorkspaceSubscription.workspace_id)
            .where(
                Workspace.type == "personal",
                Workspace.status == "active",
                WorkspaceSubscription.status == "active",
                WorkspaceSubscription.expires_at <= current,
            )
        )
    ).all()
    expired = 0
    handled_user_ids: set[uuid.UUID] = set()
    for workspace_subscription, workspace in workspace_rows:
        user = await db.get(User, workspace.owner_user_id)
        if user is None:
            continue
        workspace_subscription.status = "expired"
        user.plan = "free"
        allowance = int(PLAN_CATALOG["free"]["monthly_credits"])
        workspace_wallet = await get_or_create_personal_wallet(
            db,
            user=user,
            workspace=workspace,
            lock=True,
        )
        workspace_wallet.plan_credits = allowance
        workspace_wallet.credit_period_start = current
        await sync_legacy_wallet_mirror(
            db,
            user=user,
            wallet=workspace_wallet,
        )
        legacy_subscriptions = (
            await db.execute(
                select(UserSubscription).where(
                    UserSubscription.user_id == user.id,
                    UserSubscription.status == "active",
                )
            )
        ).scalars().all()
        for legacy in legacy_subscriptions:
            legacy.status = "expired"
        if not legacy_subscriptions:
            db.add(
                UserSubscription(
                    user_id=user.id,
                    plan=workspace_subscription.plan,
                    status="expired",
                    starts_at=workspace_subscription.starts_at,
                    expires_at=workspace_subscription.expires_at,
                    source=workspace_subscription.source,
                )
            )
        handled_user_ids.add(user.id)
        expired += 1

    subscriptions = (
        await db.execute(
            select(UserSubscription).where(
                UserSubscription.status == "active",
                UserSubscription.expires_at <= current,
                UserSubscription.user_id.not_in(handled_user_ids),
            )
        )
    ).scalars().all()
    for subscription in subscriptions:
        subscription.status = "expired"
        user = await db.get(User, subscription.user_id)
        if user is None:
            continue
        user.plan = "free"
        personal_workspace = await _personal_workspace_for_user(db, user)
        if personal_workspace is not None:
            active_workspace_subscriptions = (
                await db.execute(
                    select(WorkspaceSubscription).where(
                        WorkspaceSubscription.workspace_id
                        == personal_workspace.id,
                        WorkspaceSubscription.status == "active",
                    )
                )
            ).scalars().all()
            for workspace_subscription in active_workspace_subscriptions:
                workspace_subscription.status = "expired"
        await apply_monthly_allowance(db, user, now=current, force=True)
        expired += 1
    await db.flush()
    return expired


async def get_active_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> UserSubscription | None:
    current = now or datetime.now(timezone.utc)
    user = await db.get(User, user_id)
    if user is None:
        return None
    personal_workspace = await get_personal_workspace(db, user)
    workspace_subscription, _created = await _ensure_workspace_subscription(
        db,
        user=user,
        workspace=personal_workspace,
        now=current,
    )
    if workspace_subscription is not None:
        return await _sync_legacy_subscription(
            db,
            user=user,
            workspace_subscription=workspace_subscription,
        )
    return (
        await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > current,
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def has_active_paid_plan(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> bool:
    if user.plan not in {"standard", "professional"}:
        return False
    subscription = await get_active_subscription(db, user.id, now=now)
    # 兼容老测试/旧数据：付费 plan 还没有订阅记录时先视为有效，
    # 正式存量用户由迁移补 30 天订阅。
    return subscription is not None or user.credit_period_start is None


def _period_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def _included_limit(user: User, feature: str) -> int:
    if feature in ANALYSIS_LIMITS:
        return ANALYSIS_LIMITS[feature]
    if feature == "manual_store_check":
        return MANUAL_STORE_CHECK_LIMITS.get(user.plan, 0)
    if feature in {"product_scrape", "radar_scrape"}:
        return PRODUCT_SCRAPE_LIMITS.get(user.plan, 0)
    return 0


async def feature_allowance_snapshot(
    db: AsyncSession,
    user: User,
    feature: str,
    *,
    now: datetime | None = None,
) -> dict:
    """返回当期额度快照，供外部抓取在扣积分前预检。"""
    current = now or datetime.now(timezone.utc)
    period = _period_key(current)
    counter = (
        await db.execute(
            select(FeatureUsageCounter).where(
                FeatureUsageCounter.user_id == user.id,
                FeatureUsageCounter.feature == feature,
                FeatureUsageCounter.period_key == period,
            )
        )
    ).scalar_one_or_none()
    used = int(counter.used or 0) if counter else 0
    limit = _included_limit(user, feature)
    return {
        "included": used < limit,
        "used": used,
        "included_limit": limit,
        "included_remaining": max(0, limit - used),
        "period_key": period,
    }


async def consume_feature_allowance(
    db: AsyncSession,
    user: User,
    feature: str,
    *,
    now: datetime | None = None,
    overage_credits: int = 1,
) -> dict:
    current = now or datetime.now(timezone.utc)
    period = _period_key(current)
    counter = (
        await db.execute(
            select(FeatureUsageCounter)
            .where(
                FeatureUsageCounter.user_id == user.id,
                FeatureUsageCounter.feature == feature,
                FeatureUsageCounter.period_key == period,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if counter is None:
        counter = FeatureUsageCounter(
            user_id=user.id,
            feature=feature,
            period_key=period,
            used=0,
        )
        db.add(counter)
        await db.flush()

    limit = _included_limit(user, feature)
    included = counter.used < limit
    charged = 0
    if included:
        counter.used += 1
        await db.flush()
    else:
        await user.deduct_credits(
            db,
            overage_credits,
            feature=f"{feature}_overage",
            reference_type="usage_period",
            reference_id=period,
            description=f"{feature} 超出免费额度",
        )
        counter.used += 1
        charged = overage_credits
        await db.flush()
    return {
        "charged": charged,
        "used": counter.used,
        "included_limit": limit,
        "included_remaining": max(0, limit - counter.used),
        "period_key": period,
    }


def plan_wallet_response(user: User, wallet: CreditWallet, subscription: UserSubscription | None) -> dict:
    return {
        "plan": user.plan,
        "plan_credits": wallet.plan_credits,
        "purchased_credits": wallet.purchased_credits,
        "total_credits": wallet_total(wallet),
        "credit_period_start": str(user.credit_period_start) if user.credit_period_start else None,
        "plan_expires_at": str(subscription.expires_at) if subscription else None,
        "subscription_status": subscription.status if subscription else "free",
    }
