"""把个人用户账务幂等回填到个人工作区。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription


def _bucket() -> dict:
    return {
        "created": 0,
        "would_create": 0,
        "skipped": 0,
        "conflicts": 0,
        "missing": 0,
        "conflict_workspace_ids": [],
    }


def _add_conflict(bucket: dict, workspace_id: UUID) -> None:
    bucket["conflicts"] += 1
    if len(bucket["conflict_workspace_ids"]) < 20:
        bucket["conflict_workspace_ids"].append(str(workspace_id))


def _same_datetime(left: datetime, right: datetime) -> bool:
    """比较时间时统一到 UTC，兼容 SQLite 返回的朴素时间。"""

    def normalize(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )

    return normalize(left) == normalize(right)


async def backfill_personal_workspace_billing(
    db: AsyncSession,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    """扫描个人工作区并复制钱包与有效订阅，冲突只报告不覆盖。"""

    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    current = now or datetime.now(timezone.utc)
    wallets = _bucket()
    subscriptions = _bucket()
    checked = 0
    cursor: UUID | None = None

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
        for workspace in workspaces:
            owner_id = workspace.owner_user_id
            owner = (
                await db.get(User, owner_id)
                if owner_id is not None
                else None
            )
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

            if legacy_wallet is None:
                wallets["missing"] += 1
            elif workspace_wallet is None:
                wallets["would_create" if dry_run else "created"] += 1
                if not dry_run:
                    db.add(
                        WorkspaceCreditWallet(
                            workspace_id=workspace.id,
                            plan_credits=legacy_wallet.plan_credits,
                            purchased_credits=legacy_wallet.purchased_credits,
                            credit_period_start=(
                                owner.credit_period_start
                                if owner is not None
                                else None
                            ),
                        )
                    )
            elif (
                workspace_wallet.plan_credits
                == legacy_wallet.plan_credits
                and workspace_wallet.purchased_credits
                == legacy_wallet.purchased_credits
            ):
                wallets["skipped"] += 1
            else:
                _add_conflict(wallets, workspace.id)

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

            if legacy_subscription is None:
                subscriptions["missing"] += 1
            elif workspace_subscription is None:
                subscriptions["would_create" if dry_run else "created"] += 1
                if not dry_run:
                    db.add(
                        WorkspaceSubscription(
                            workspace_id=workspace.id,
                            plan=legacy_subscription.plan,
                            status="active",
                            starts_at=legacy_subscription.starts_at,
                            expires_at=legacy_subscription.expires_at,
                            payer_user_id=owner_id,
                            source="legacy_workspace_backfill",
                        )
                    )
            elif (
                workspace_subscription.plan == legacy_subscription.plan
                and _same_datetime(
                    workspace_subscription.starts_at,
                    legacy_subscription.starts_at,
                )
                and _same_datetime(
                    workspace_subscription.expires_at,
                    legacy_subscription.expires_at,
                )
            ):
                subscriptions["skipped"] += 1
            else:
                _add_conflict(subscriptions, workspace.id)

        # 每批刷新，后续查询可以看到本批已创建的数据。
        if not dry_run:
            await db.flush()

    return {
        "workspaces_checked": checked,
        "dry_run": dry_run,
        "wallets": wallets,
        "subscriptions": subscriptions,
    }
