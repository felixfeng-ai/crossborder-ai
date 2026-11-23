"""VeyaShip - FastAPI 依赖注入

【全栈学习者必读】
"依赖注入"（Dependency Injection）是 FastAPI 最核心的概念。
理解它，就理解了 FastAPI 的架构精髓。

什么是依赖注入？
- 路由函数需要的"东西"，不自己创建，而是声明"我需要什么"
- FastAPI 自动把需要的东西传进来
- 就像去餐厅：你不自己种菜做饭，你点菜（声明依赖），服务员（FastAPI）给你端上来

常见的依赖：
- get_db: 给路由一个数据库会话
- get_current_user: 从 JWT token 解析出当前登录用户
- RateLimit: 检查请求是否超过频率限制

依赖注入的好处：
- 解耦：路由函数不需要知道如何创建数据库连接
- 复用：多个路由共享同一个依赖
- 测试：可以替换依赖（如用测试数据库代替真实数据库）
- 可维护：修改依赖实现，所有路由自动生效
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.models.user_session import UserSession
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspaces import (
    ensure_personal_workspace,
    get_workspace_membership,
)
from app.services.personal_billing import refresh_personal_billing_mirror

# ── OAuth2 密码流配置 ──────────────────────────────────────────
# OAuth2PasswordBearer 告诉 FastAPI：
# "客户端应该把 token 放在 HTTP Header 里：
#   Authorization: Bearer <token>"
#
# tokenUrl 指定了获取 token 的 API 路径（用户登录的接口）
# auto_error=False 表示如果没有 token，不自动报错，而是传 None
# 这样有些接口可以"有 token 就认证，没有也允许访问"
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """【核心】从 JWT token 解析出当前登录用户。

    这是最常用的依赖，几乎所有需要登录的接口都用它。

    执行流程：
    1. FastAPI 从 HTTP Header 提取 Bearer token
    2. decode_token() 验证 JWT 签名和过期时间
    3. 取出 payload.sub 里的用户 ID
    4. 查数据库找到对应的 User 对象
    5. 返回 User 对象给路由函数

    路由中使用：
        @router.get("/profile")
        async def get_profile(current_user: User = Depends(get_current_user)):
            return {"username": current_user.username}
        # 不需要手动解析 token！不需要自己查数据库！
        # FastAPI 自动搞定这一切

    Args:
        token: JWT 令牌（自动从请求头提取）
        db: 数据库会话（自动创建和释放）

    Returns:
        当前登录的 User 对象

    Raises:
        HTTPException 401: 未提供 token / token 无效 / 用户不存在
    """
    # 第一步：检查是否有 token
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录，请先登录",
        )

    # 第二步：解码 token，提取用户 ID
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("invalid token type")
        user_id_str: str | None = payload.get("sub")
        session_id_str: str | None = payload.get("sid")
        if user_id_str is None or session_id_str is None:
            raise ValueError("invalid token payload")
        # 把字符串 ID 转成 UUID 对象（数据库用 UUID 做主键）
        user_id = UUID(user_id_str)
        session_id = UUID(session_id_str)
    except (JWTError, ValueError):
        # JWTError = 签名无效或已过期
        # ValueError = UUID 格式不对
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )

    session = await db.get(UserSession, session_id)
    now = datetime.now(timezone.utc)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or (
            session.expires_at
            if session.expires_at.tzinfo
            else session.expires_at.replace(tzinfo=timezone.utc)
        ) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录会话已失效，请重新登录",
        )

    # 第三步：查数据库，确认用户还存在
    # 这一步不是必须的（JWT 本身已经够安全），
    # 但可以拦截"用户已被删除"的情况
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已注销",
        )

    await refresh_personal_billing_mirror(db, user)

    # 挂到 request.state，供后续依赖（如 RateLimit）读取，实现按用户粒度限流。
    # 注意：RateLimit 依赖必须在路由签名里声明在 get_current_user 之后才会先跑到这里。
    request.state.user = user
    request.state.auth_session_id = session.id
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """管理员权限依赖：邮箱必须在 ADMIN_EMAILS 配置里。

    用于套餐升级审批等后台操作。校验在前端只是隐藏入口，
    真正的权限边界在后端这里强制。
    """
    admin_emails = {e.lower() for e in settings.ADMIN_EMAILS}
    if current_user.email.lower() not in admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可执行此操作",
        )
    return current_user


@dataclass(frozen=True)
class WorkspaceContext:
    workspace: Workspace
    membership: WorkspaceMember
    explicit: bool = False

    @property
    def role(self) -> str:
        return self.membership.role


async def get_current_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceContext:
    """验证路径中的工作区属于当前用户。"""

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="工作区不存在")
    membership = await get_workspace_membership(
        db,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="工作区不存在")
    return WorkspaceContext(
        workspace=workspace,
        membership=membership,
        explicit=True,
    )


async def get_web_workspace(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceContext:
    """兼容旧 Web：显式请求头优先，否则使用用户个人工作区。"""

    raw_workspace_id = request.headers.get("X-Workspace-Id")
    if raw_workspace_id:
        try:
            workspace_id = UUID(raw_workspace_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="工作区不存在",
            ) from exc
        workspace = await db.get(Workspace, workspace_id)
    else:
        workspace = await ensure_personal_workspace(db, current_user)

    if workspace is None or workspace.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="工作区不存在",
        )
    membership = await get_workspace_membership(
        db,
        workspace_id=workspace.id,
        user_id=current_user.id,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="工作区不存在",
        )
    return WorkspaceContext(
        workspace=workspace,
        membership=membership,
        explicit=bool(raw_workspace_id),
    )


def require_workspace_role(*allowed_roles: str):
    """生成工作区角色依赖。"""

    async def dependency(
        context: WorkspaceContext = Depends(get_current_workspace),
    ) -> WorkspaceContext:
        if context.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="没有工作区操作权限")
        return context

    return dependency
