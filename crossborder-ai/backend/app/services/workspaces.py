"""工作区领域服务。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


def _display_name(user: User) -> str:
    username = (user.username or "").strip()
    if username:
        return username
    return user.email.split("@", 1)[0]


async def ensure_personal_workspace(
    db: AsyncSession,
    user: User,
) -> Workspace:
    """返回用户个人工作区，不存在时创建所有者成员关系。"""

    existing = (
        await db.execute(
            select(Workspace).where(
                Workspace.owner_user_id == user.id,
                Workspace.type == "personal",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    workspace = Workspace(
        name=f"{_display_name(user)}的工作区",
        slug=f"personal-{user.id.hex[:12]}",
        type="personal",
        owner_user_id=user.id,
        status="active",
        settings_json="{}",
    )
    db.add(workspace)
    await db.flush()

    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
    )
    await db.flush()
    return workspace


async def get_workspace_membership(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceMember | None:
    """仅返回有效工作区中的有效成员关系。"""

    return (
        await db.execute(
            select(WorkspaceMember)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.status == "active",
                Workspace.status == "active",
            )
        )
    ).scalar_one_or_none()


async def bootstrap_personal_workspaces(
    db: AsyncSession,
    *,
    batch_size: int = 500,
) -> dict[str, int]:
    """为缺少个人工作区的用户补齐所有者工作区。"""

    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")

    created = 0
    skipped = 0
    failed = 0
    offset = 0

    personal_owner_ids = set(
        (
            await db.execute(
                select(Workspace.owner_user_id).where(
                    Workspace.type == "personal"
                )
            )
        ).scalars().all()
    )

    while True:
        users = (
            await db.execute(
                select(User)
                .order_by(User.id)
                .offset(offset)
                .limit(batch_size)
            )
        ).scalars().all()
        if not users:
            break

        for user in users:
            if user.id in personal_owner_ids:
                skipped += 1
                continue
            try:
                async with db.begin_nested():
                    await ensure_personal_workspace(db, user)
                personal_owner_ids.add(user.id)
                created += 1
            except Exception:
                failed += 1

        offset += len(users)

    return {
        "created": created,
        "skipped": skipped,
        "failed": failed,
    }


async def list_user_workspaces(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> list[tuple[Workspace, WorkspaceMember]]:
    rows = (
        await db.execute(
            select(Workspace, WorkspaceMember)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.id,
            )
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.status == "active",
                Workspace.status == "active",
            )
            .order_by(Workspace.type.desc(), Workspace.name)
        )
    ).all()
    return [(workspace, member) for workspace, member in rows]
