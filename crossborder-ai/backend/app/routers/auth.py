"""VeyaShip - 用户认证路由

【全栈学习者必读】
这个文件展示了后端的"增删改查"中最基础的操作：
1. SELECT 查询 — 注册时检查邮箱是否已注册
2. INSERT 写入 — 创建新用户
3. JWT 签发 — 认证通过后发放"通行证"
4. 依赖注入 — 用 get_current_user 从 token 获取用户

路由设计模式（RESTful API）：
- POST /register — 创建资源（不是 GET，因为会改变服务器状态）
- POST /login — 也是创建资源（创建 token）
- GET /me — 读取资源

为什么注册用 POST 不是 PUT？
- POST 创建资源，服务器决定 ID（UUID）
- PUT 创建/更新资源，客户端指定 ID
- 这里的 user.id 是自动生成的 UUID，所以用 POST
"""

from datetime import datetime, timezone
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.core.security import (
    hash_password,
    verify_password,
)
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth_sessions import (
    RefreshTokenRejected,
    create_user_session,
    list_active_sessions,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
)
from app.services.credit_service import apply_monthly_allowance
from app.services.user_lifecycle import delete_user_account
from app.services.user_profiles import build_user_response
from app.services.workspaces import ensure_personal_workspace

# ── 创建路由实例 ──────────────────────────────────────────────
# prefix="/auth" 表示这个路由下的所有接口都以 /api/v1/auth 开头
# （main.py 中设置了 API_PREFIX="/api/v1"+ prefix）
# tags 用于 API 文档（/docs）的分组
router = APIRouter(prefix="/auth", tags=["用户认证"])
USERNAME_PATTERN = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9_]{4,12}$")


def _device_metadata(request: Request) -> dict[str, str | None]:
    """记录可展示的设备信息，不接受可执行指纹或隐私字段。"""

    return {
        "device_name": request.headers.get("X-Device-Name"),
        "platform": request.headers.get("X-Device-Platform"),
        "client_version": request.headers.get("X-Client-Version"),
    }


async def _issue_session(db, request: Request, user: User) -> TokenResponse:
    payload = await create_user_session(
        db,
        user,
        **_device_metadata(request),
    )
    return TokenResponse(**payload)


class AccountDeletionRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)
    confirmation: Literal["注销账号"]


class UsernameAvailabilityResponse(BaseModel):
    username: str
    available: bool


@router.get(
    "/username-availability",
    response_model=UsernameAvailabilityResponse,
)
async def username_availability(
    username: str = Query(..., min_length=1, max_length=32),
    _ratelimit=Depends(RateLimit("auth")),
    db: AsyncSession = Depends(get_db),
):
    """检查注册用户名是否可用，不返回其他账号信息。"""

    normalized = username.strip()
    if USERNAME_PATTERN.fullmatch(normalized) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="称呼需为 4–12 位中文、字母、数字或下划线",
        )
    result = await db.execute(
        select(User.id)
        .where(
            func.lower(User.username) == normalized.lower(),
            User.deleted_at.is_(None),
        )
        .limit(1)
    )
    return UsernameAvailabilityResponse(
        username=normalized,
        available=result.scalar_one_or_none() is None,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    request: Request,
    # _ratelimit 前导下划线表示"这个参数在函数里没用到"
    # RateLimit("auth") 是限流依赖：同一 IP 5秒内最多请求 5 次
    # Depends() 是 FastAPI 依赖注入的关键字
    _ratelimit=Depends(RateLimit("auth")),
    # get_db 获取数据库会话，所有数据库操作都通过它
    db: AsyncSession = Depends(get_db),
):
    """注册新用户

    【全栈学习者重点理解】
    请求到响应的完整流程：
    1. FastAPI 收到 POST /api/v1/auth/register
    2. 自动验证请求体是否符合 UserCreate 的格式
    3. 自动从 RateLimit("auth") 检查请求频率
    4. 自动从 get_db() 创建数据库会话
    5. 执行函数体中的代码
    6. 自动把返回值序列化为 TokenResponse 格式
    7. 如果一切正常，自动 commit 事务
    8. 如果抛异常，自动 rollback

    Args:
        payload: 请求体（FastAPI 自动从 JSON 解析）
        request: HTTP 请求对象（FastAPI 自动传入）
        db: 数据库会话（FastAPI 通过依赖注入传入）

    Returns:
        TokenResponse: 包含 JWT 访问令牌

    Raises:
        HTTPException 409: 邮箱已被注册
    """
    # ── Step 1: SELECT 检查邮箱是否已存在 ──────────────────
    # SQL: SELECT * FROM users WHERE email = ? LIMIT 1
    # 这是"防止重复注册"的标准做法
    result = await db.execute(select(User).where(User.email == payload.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已被注册",
        )

    if payload.username:
        normalized_username = payload.username.strip()
        username_result = await db.execute(
            select(User.id)
            .where(
                func.lower(User.username) == normalized_username.lower(),
                User.deleted_at.is_(None),
            )
            .limit(1)
        )
        if username_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="这个称呼已经被用了",
            )

    # ── Step 2: INSERT 创建新用户 ───────────────────────────
    # 1. 创建 User 对象（内存中）
    # 2. db.add() 加入会话跟踪
    # 3. db.flush() 写入数据库（但不提交事务）
    #    需要 flush 是因为 User.id 是自动生成的 UUID
    #    不 flush 的话，user.id 是 None
    #
    # password_hash: 存的是 bcrypt 哈希，不是明文！
    # 即使数据库被拖库，攻击者也拿不到密码原文
    user = User(
        email=payload.email,
        username=payload.username or payload.email.split("@")[0],
        password_hash=hash_password(payload.password),
        credits=0,
    )
    db.add(user)
    await db.flush()
    await apply_monthly_allowance(db, user)
    await ensure_personal_workspace(db, user)

    return await _issue_session(db, request, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserCreate,
    request: Request,
    _ratelimit=Depends(RateLimit("auth")),
    db: AsyncSession = Depends(get_db),
):
    """用户登录

    流程：
    1. 用邮箱查用户
    2. 验证密码（不是简单的 ==，是用 bcrypt 校验哈希）
    3. 签发 JWT token

    为什么登录要单独一个接口？
    - 登录和注册的验证逻辑不同（注册要检查重复，登录要验证密码）
    - 未来可能加"验证码"、"记住我"等功能
    - 符合 REST 规范：不同操作不同端点

    Args:
        payload: 包含 email 和 password

    Returns:
        TokenResponse: JWT 访问令牌
    """
    # ── 查用户 ─────────────────────────────────────────────
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # ── 验证密码 ───────────────────────────────────────────
    # 为什么不直接告诉用户"邮箱不存在"或"密码错误"？
    # 安全考虑：防止攻击者枚举哪个邮箱已注册
    # 统一返回"邮箱或密码错误"让攻击者无法区分
    if (
        not user
        or user.deleted_at is not None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    await ensure_personal_workspace(db, user)

    return await _issue_session(db, request, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """一次性刷新令牌轮换；重放会撤销整个设备会话。"""

    try:
        tokens = await rotate_refresh_token(db, payload.refresh_token)
        await db.commit()
        return TokenResponse(**tokens)
    except RefreshTokenRejected as exc:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_current_session(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只撤销当前设备会话。"""

    await revoke_session(
        db,
        session_id=request.state.auth_session_id,
        user_id=current_user.id,
        reason="user_logout",
    )
    await db.commit()
    return None


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销当前用户全部设备会话。"""

    await revoke_all_sessions(
        db,
        user_id=current_user.id,
        reason="user_logout_all",
    )
    await db.commit()
    return None


@router.get("/sessions")
async def get_active_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前账号仍有效的设备会话。"""

    sessions = await list_active_sessions(db, user_id=current_user.id)
    current_id = request.state.auth_session_id
    return {
        "items": [
            {
                "id": str(session.id),
                "device_name": session.device_name,
                "platform": session.platform,
                "client_version": session.client_version,
                "created_at": str(session.created_at),
                "last_used_at": str(session.last_used_at),
                "expires_at": str(session.expires_at),
                "current": session.id == current_id,
            }
            for session in sessions
        ]
    }


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_specific_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销当前用户的指定设备；其他用户会话统一 404。"""

    from uuid import UUID

    try:
        parsed_id = UUID(session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="设备会话不存在",
        ) from exc
    revoked = await revoke_session(
        db,
        session_id=parsed_id,
        user_id=current_user.id,
        reason="user_revoked_device",
    )
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="设备会话不存在",
        )
    await db.commit()
    return None


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """改密后撤销全部旧会话，并给当前设备签发新会话。"""

    if not verify_password(
        payload.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )
    current_user.password_hash = hash_password(payload.new_password)
    await revoke_all_sessions(
        db,
        user_id=current_user.id,
        reason="password_changed",
    )
    return await _issue_session(db, request, current_user)


@router.post("/delete-account")
async def delete_account(
    payload: AccountDeletionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """校验密码后逻辑注销账号，并保留工作区业务数据。"""

    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误，未执行注销",
        )
    result = await delete_user_account(
        db,
        user_id=current_user.id,
        reason="user_requested",
    )
    await db.commit()
    return result


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户的信息

    这个接口展示了"依赖注入"的真正威力：
    路由函数本身一行代码都没写用户查询逻辑！
    全部由 get_current_user 依赖完成：
    1. 从 HTTP Header 提取 token
    2. 解码 JWT，取出用户 ID
    3. 查数据库，返回 User 对象

    路由只需要声明 current_user: User = Depends(get_current_user)
    就可以直接用 current_user 了。

    这样做的价值：
    - 所有需要登录的接口都复用同一套认证逻辑
    - 如果要改认证方式（比如加 Redis 缓存），只改一个地方
    - 测试时可以 mock 这个依赖

    Args:
        current_user: 当前登录的用户（FastAPI 自动注入）

    Returns:
        UserResponse: 用户信息（不会暴露密码哈希）
    """
    applied = await apply_monthly_allowance(db, current_user)
    if applied is not None:
        await db.commit()
        await db.refresh(current_user)

    return build_user_response(current_user)


class WeChatLoginRequest(BaseModel):
    code: str = Field(..., description="微信小程序 wx.login() 返回的 code")


@router.post("/wx-login", response_model=TokenResponse)
async def wechat_login(
    payload: WeChatLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """微信小程序登录

    流程：
    1. 小程序调 wx.login() 获取 code
    2. 后端用 code 向微信服务器换 openid
    3. 查找或创建用户
    4. 返回 JWT token
    """
    import httpx

    app_id = settings.WEIXIN_APP_ID
    app_secret = settings.WEIXIN_APP_SECRET
    if not app_id or not app_secret:
        raise HTTPException(status_code=400, detail="微信登录未配置")

    # 向微信服务器换 openid
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": app_id,
                "secret": app_secret,
                "js_code": payload.code,
                "grant_type": "authorization_code",
            },
        )
        data = resp.json()
        if "openid" not in data:
            raise HTTPException(status_code=400, detail="微信登录失败")

        openid = data["openid"]

    # 查找或创建用户
    result = await db.execute(select(User).where(User.email == f"wx_{openid}@weixin.com"))
    user = result.scalar_one_or_none()

    if not user:
        import uuid
        user = User(
            email=f"wx_{openid}@weixin.com",
            username=f"wx_{openid[:8]}",
            password_hash=hash_password(str(uuid.uuid4())),
        )
        db.add(user)
        await db.flush()

    await ensure_personal_workspace(db, user)
    return await _issue_session(db, request, user)
