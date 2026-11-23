"""用户逻辑注销与工作区归档生命周期。"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.admin_audit_log import AdminAuditLog
from app.models.agent_task import AgentTask
from app.models.agent_policy import ActionApproval
from app.models.agent_work import WorkItemCommand
from app.models.audio_asset import AudioAsset
from app.models.batch_job import BatchJob
from app.models.content import ContentGeneration
from app.models.conversation import Conversation
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.listing import Listing
from app.models.listing_draft import ListingDraft
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import (
    MarketingCampaignPublication,
    MarketingPerformanceSnapshot,
)
from app.models.marketing_image_suite import MarketingImageSuite
from app.models.marketing_video import MarketingVideoProject
from app.models.operation_alert import OperationAlert
from app.models.persona import Persona
from app.models.platform_connection import PlatformConnection
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.shopify_channel import ShopifyChannel
from app.models.store_check_log import StoreCheckLog
from app.models.user import User
from app.models.variant_snapshot import VariantSnapshot
from app.models.video_generation_task import VideoGenerationTask
from app.models.voc import VocAnalysis
from app.models.workspace import Workspace, WorkspaceAuditLog, WorkspaceMember
from app.services.workspaces import ensure_personal_workspace
from app.services.auth_sessions import revoke_all_sessions
from app.models.notification import MobileDevice, NotificationPreference


class WorkspaceLifecycleError(ValueError):
    """工作区生命周期状态不允许当前操作。"""


async def _archive_workspace(
    db: AsyncSession,
    *,
    workspace: Workspace,
    actor_user_id: UUID,
    reason: str,
    now: datetime,
    retention_days: int,
) -> None:
    """归档工作区并保留业务数据，等待恢复或到期清理。"""

    workspace.status = "archived"
    workspace.owner_user_id = None
    workspace.archived_at = now
    workspace.purge_after = now + timedelta(days=retention_days)
    workspace.archived_by_user_id = actor_user_id
    db.add(
        WorkspaceAuditLog(
            workspace_id=workspace.id,
            actor_user_id=actor_user_id,
            action="workspace.archived",
            resource_type="workspace",
            resource_id=str(workspace.id),
            after_json=(
                f'{{"reason":"{reason}",'
                f'"purge_after":"{workspace.purge_after.isoformat()}"}}'
            ),
        )
    )


async def _transfer_workspace_owner(
    db: AsyncSession,
    *,
    workspace: Workspace,
    current_owner_id: UUID,
) -> WorkspaceMember | None:
    """优先把团队工作区转交给仍在用的管理员。"""

    membership = (
        await db.execute(
            select(WorkspaceMember)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id != current_owner_id,
                WorkspaceMember.status == "active",
                WorkspaceMember.role.in_(("owner", "admin")),
                User.deleted_at.is_(None),
            )
            .order_by(
                case(
                    (WorkspaceMember.role == "owner", 0),
                    else_=1,
                ),
                WorkspaceMember.joined_at,
            )
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if membership is None:
        return None

    workspace.owner_user_id = membership.user_id
    membership.role = "owner"
    db.add(
        WorkspaceAuditLog(
            workspace_id=workspace.id,
            actor_user_id=current_owner_id,
            action="workspace.owner_transferred",
            resource_type="workspace",
            resource_id=str(workspace.id),
            after_json=(
                f'{{"new_owner_user_id":"{membership.user_id}"}}'
            ),
        )
    )
    return membership


async def _detach_user_workspace_data(
    db: AsyncSession,
    *,
    user_id: UUID,
    workspace_ids: list[UUID],
) -> None:
    """解除用户身份与工作区业务数据的关联，但不删除业务记录。"""

    if not workspace_ids:
        return
    actor_targets = (
        (Product, "user_id", ("created_by_user_id",)),
        (ProductVariant, "user_id", ("created_by_user_id",)),
        (Listing, "owner_id", ("created_by_user_id",)),
        (ListingDraft, "user_id", ("created_by_user_id",)),
        (ImageAsset, "user_id", ()),
        (AudioAsset, "user_id", ()),
        (ImageGenerationTask, "user_id", ()),
        (VideoGenerationTask, "user_id", ()),
        (MarketingCampaign, "user_id", ()),
        (MarketingCopyAsset, "user_id", ()),
        (MarketingImageSuite, "user_id", ()),
        (MarketingVideoProject, "user_id", ()),
        (MarketingCampaignPublication, "user_id", ()),
        (MarketingPerformanceSnapshot, "user_id", ()),
        (Persona, "user_id", ()),
        (ShopifyChannel, "user_id", ()),
        (ContentGeneration, "user_id", ()),
        (BatchJob, "user_id", ()),
        (StoreCheckLog, "user_id", ()),
        (OperationAlert, "user_id", ()),
        (VariantSnapshot, "user_id", ()),
        (Publication, "user_id", ()),
        (VocAnalysis, "user_id", ()),
        (AgentTask, "user_id", ()),
        (Conversation, "user_id", ()),
        (ActionApproval, "user_id", ()),
        (WorkItemCommand, "actor_user_id", ()),
    )
    for model, owner_field, extra_fields in actor_targets:
        values = {field: None for field in extra_fields}
        values[owner_field] = None
        await db.execute(
            update(model)
            .where(
                getattr(model, owner_field) == user_id,
                model.workspace_id.in_(workspace_ids),
            )
            .values(**values)
        )


async def restore_workspace(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    new_owner_user_id: UUID,
    actor_user_id: UUID,
    now: datetime | None = None,
) -> dict:
    """在保留期内把归档工作区恢复给新的有效所有者。"""

    current = now or datetime.now(timezone.utc)
    workspace = (
        await db.execute(
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise WorkspaceLifecycleError("工作区不存在")
    if workspace.status != "archived":
        raise WorkspaceLifecycleError("只有归档工作区可以恢复")
    if workspace.purge_after is not None and workspace.purge_after <= current:
        raise WorkspaceLifecycleError("工作区已超过恢复期限")

    successor = (
        await db.execute(
            select(User)
            .where(
                User.id == new_owner_user_id,
                User.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if successor is None:
        raise WorkspaceLifecycleError("新所有者不是有效用户")

    other_owners = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "owner",
            )
        )
    ).scalars().all()
    for membership in other_owners:
        if membership.user_id != new_owner_user_id:
            membership.role = "admin"

    membership = await db.get(
        WorkspaceMember,
        (workspace_id, new_owner_user_id),
    )
    if membership is None:
        membership = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=new_owner_user_id,
            role="owner",
            status="active",
        )
        db.add(membership)
    else:
        membership.role = "owner"
        membership.status = "active"

    workspace.status = "active"
    workspace.owner_user_id = new_owner_user_id
    workspace.archived_at = None
    workspace.purge_after = None
    workspace.archived_by_user_id = None
    db.add(
        AdminAuditLog(
            admin_user_id=actor_user_id,
            action="workspace.lifecycle.restore",
            target_type="workspace",
            target_id=str(workspace_id),
            changes_json=(
                f'{{"new_owner_user_id":"{new_owner_user_id}"}}'
            ),
        )
    )
    await db.flush()
    return {
        "restored": True,
        "workspace_id": str(workspace_id),
        "owner_user_id": str(new_owner_user_id),
    }


async def purge_workspace(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    now: datetime | None = None,
) -> dict:
    """只清理已归档且到期的完整工作区。"""

    current = now or datetime.now(timezone.utc)
    workspace = (
        await db.execute(
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if workspace is None:
        raise WorkspaceLifecycleError("工作区不存在")
    if workspace.status != "archived":
        raise WorkspaceLifecycleError("只有归档工作区可以清理")
    if workspace.purge_after is None or workspace.purge_after > current:
        raise WorkspaceLifecycleError("工作区尚未到清理时间")

    db.add(
        AdminAuditLog(
            admin_user_id=None,
            action="workspace.lifecycle.purge",
            target_type="workspace",
            target_id=str(workspace_id),
            changes_json=(
                f'{{"purged_at":"{current.isoformat()}"}}'
            ),
        )
    )
    await db.delete(workspace)
    await db.flush()
    return {
        "purged": True,
        "workspace_id": str(workspace_id),
    }


async def purge_expired_workspaces(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
) -> dict:
    """按批清理已到期归档工作区，未到期数据保持不动。"""

    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    current = now or datetime.now(timezone.utc)
    workspace_ids = (
        await db.execute(
            select(Workspace.id)
            .where(
                Workspace.status == "archived",
                Workspace.purge_after.is_not(None),
                Workspace.purge_after <= current,
            )
            .order_by(Workspace.purge_after, Workspace.id)
            .limit(batch_size)
        )
    ).scalars().all()
    purged: list[str] = []
    for workspace_id in workspace_ids:
        await purge_workspace(
            db,
            workspace_id=workspace_id,
            now=current,
        )
        purged.append(str(workspace_id))
    return {
        "purged_count": len(purged),
        "purged_workspace_ids": purged,
    }


async def run_user_lifecycle_drill(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict:
    """在调用方事务内完成一次可回滚的完整生命周期演练。"""

    current = now or datetime.now(timezone.utc)
    drill_id = uuid.uuid4().hex[:10]
    owner = User(
        email=f"lifecycle-drill-owner-{drill_id}@invalid.local",
        username=f"lifecycle-owner-{drill_id}",
        password_hash="not-used",
        plan="standard",
        credits=50,
    )
    successor = User(
        email=f"lifecycle-drill-successor-{drill_id}@invalid.local",
        username=f"lifecycle-successor-{drill_id}",
        password_hash="not-used",
        plan="free",
    )
    member = User(
        email=f"lifecycle-drill-member-{drill_id}@invalid.local",
        username=f"lifecycle-member-{drill_id}",
        password_hash="not-used",
        plan="free",
    )
    db.add_all([owner, successor, member])
    await db.flush()

    personal = await ensure_personal_workspace(db, owner)
    team = Workspace(
        name=f"Lifecycle Drill Team {drill_id}",
        slug=f"lifecycle-drill-team-{drill_id}",
        type="team",
        owner_user_id=owner.id,
        status="active",
    )
    orphan_team = Workspace(
        name=f"Lifecycle Drill Orphan {drill_id}",
        slug=f"lifecycle-drill-orphan-{drill_id}",
        type="team",
        owner_user_id=member.id,
        status="active",
    )
    db.add_all([team, orphan_team])
    await db.flush()
    db.add_all(
        [
            WorkspaceMember(
                workspace_id=team.id,
                user_id=owner.id,
                role="owner",
                status="active",
            ),
            WorkspaceMember(
                workspace_id=team.id,
                user_id=successor.id,
                role="admin",
                status="active",
            ),
            WorkspaceMember(
                workspace_id=team.id,
                user_id=member.id,
                role="operator",
                status="active",
            ),
            WorkspaceMember(
                workspace_id=orphan_team.id,
                user_id=member.id,
                role="owner",
                status="active",
            ),
        ]
    )
    personal_product = Product(
        user_id=owner.id,
        workspace_id=personal.id,
        created_by_user_id=owner.id,
        title=f"Lifecycle drill personal {drill_id}",
        url=f"https://example.invalid/lifecycle/{drill_id}/personal",
    )
    team_product = Product(
        user_id=owner.id,
        workspace_id=team.id,
        created_by_user_id=owner.id,
        title=f"Lifecycle drill team {drill_id}",
        url=f"https://example.invalid/lifecycle/{drill_id}/team",
    )
    orphan_product = Product(
        user_id=member.id,
        workspace_id=orphan_team.id,
        created_by_user_id=member.id,
        title=f"Lifecycle drill orphan {drill_id}",
        url=f"https://example.invalid/lifecycle/{drill_id}/orphan",
    )
    db.add_all([personal_product, team_product, orphan_product])
    await db.flush()

    await delete_user_account(
        db,
        user_id=member.id,
        reason="lifecycle_drill",
        now=current,
        retention_days=1,
    )
    await db.flush()
    orphan_workspace_after_delete = await db.get(Workspace, orphan_team.id)
    orphan_status_after_delete = (
        orphan_workspace_after_delete.status
        if orphan_workspace_after_delete is not None
        else None
    )
    team_product_after_member_delete = await db.get(
        Product,
        team_product.id,
    )

    await delete_user_account(
        db,
        user_id=owner.id,
        reason="lifecycle_drill",
        now=current,
        retention_days=1,
    )
    await db.flush()
    personal_after_delete = await db.get(Workspace, personal.id)
    team_after_delete = await db.get(Workspace, team.id)
    personal_status_after_delete = (
        personal_after_delete.status
        if personal_after_delete is not None
        else None
    )

    await restore_workspace(
        db,
        workspace_id=personal.id,
        new_owner_user_id=successor.id,
        actor_user_id=successor.id,
        now=current,
    )
    restored_personal = await db.get(Workspace, personal.id)
    personal_product_after_restore = await db.get(
        Product,
        personal_product.id,
    )

    await purge_workspace(
        db,
        workspace_id=orphan_team.id,
        now=current + timedelta(days=2),
    )
    await db.flush()
    orphan_after_purge = await db.scalar(
        select(Workspace.id).where(Workspace.id == orphan_team.id)
    )
    orphan_product_after_purge = await db.scalar(
        select(Product.id).where(Product.id == orphan_product.id)
    )

    checks = {
        "member_removed": member.deleted_at is not None,
        "team_transferred": (
            team_after_delete is not None
            and team_after_delete.owner_user_id == successor.id
        ),
        "personal_archived": (
            personal_after_delete is not None
            and personal_status_after_delete == "archived"
        ),
        "workspace_data_preserved": (
            team_product_after_member_delete is not None
            and team_product_after_member_delete.workspace_id == team.id
        ),
        "personal_restored": (
            restored_personal is not None
            and restored_personal.status == "active"
            and restored_personal.owner_user_id == successor.id
            and personal_product_after_restore is not None
        ),
        "orphan_archived": (
            orphan_workspace_after_delete is not None
            and orphan_status_after_delete == "archived"
        ),
        "expired_workspace_purged": (
            orphan_after_purge is None
            and orphan_product_after_purge is None
        ),
    }
    return {
        "drill_id": drill_id,
        "checks": checks,
        "passed": all(checks.values()),
        "workspace_ids": {
            "personal": str(personal.id),
            "team": str(team.id),
            "orphan_team": str(orphan_team.id),
        },
    }


async def delete_user_account(
    db: AsyncSession,
    *,
    user_id: UUID,
    reason: str = "user_requested",
    now: datetime | None = None,
    retention_days: int | None = None,
) -> dict:
    """逻辑注销账号，不物理删除用户或工作区业务数据。"""

    current = now or datetime.now(timezone.utc)
    effective_retention_days = (
        retention_days
        if retention_days is not None
        else settings.WORKSPACE_ARCHIVE_RETENTION_DAYS
    )
    user = (
        await db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")
    if user.deleted_at is not None:
        return {
            "user_deleted": True,
            "already_deleted": True,
            "archived_workspace_ids": [],
            "transferred_workspace_ids": [],
        }

    owned_workspaces = (
        await db.execute(
            select(Workspace)
            .where(Workspace.owner_user_id == user_id)
            .order_by(Workspace.id)
            .with_for_update()
        )
    ).scalars().all()
    archived: list[UUID] = []
    transferred: list[UUID] = []
    for workspace in owned_workspaces:
        if workspace.status != "active":
            continue
        successor = None
        if workspace.type != "personal":
            successor = await _transfer_workspace_owner(
                db,
                workspace=workspace,
                current_owner_id=user_id,
            )
        if successor is not None:
            transferred.append(workspace.id)
        else:
            await _archive_workspace(
                db,
                workspace=workspace,
                actor_user_id=user_id,
                reason=reason,
                now=current,
                retention_days=max(effective_retention_days, 1),
            )
            archived.append(workspace.id)

    memberships = (
        await db.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.user_id == user_id)
            .with_for_update()
        )
    ).scalars().all()
    affected_workspace_ids = {
        workspace.id for workspace in owned_workspaces
    }
    affected_workspace_ids.update(
        membership.workspace_id for membership in memberships
    )
    for membership in memberships:
        membership.status = "removed"

    # 这些记录属于账号自身的凭据和终端，不随工作区归档保留。
    await revoke_all_sessions(
        db,
        user_id=user_id,
        reason="account_deleted",
    )
    for model in (
        MobileDevice,
        NotificationPreference,
        PlatformConnection,
    ):
        await db.execute(
            delete(model).where(model.user_id == user_id)
        )

    await _detach_user_workspace_data(
        db,
        user_id=user_id,
        workspace_ids=list(affected_workspace_ids),
    )

    user.email = f"deleted-{user.id.hex}@invalid.local"
    user.username = None
    user.password_hash = f"!deleted-{secrets.token_hex(24)}"
    user.credits = 0
    user.plan = "free"
    user.credit_period_start = None
    user.deleted_at = current
    user.deletion_reason = reason[:80]

    await db.flush()
    return {
        "user_deleted": True,
        "already_deleted": False,
        "archived_workspace_ids": [str(item) for item in archived],
        "transferred_workspace_ids": [str(item) for item in transferred],
    }
