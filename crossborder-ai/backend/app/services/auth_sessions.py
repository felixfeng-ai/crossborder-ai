"""设备会话、短期访问令牌和一次性刷新令牌。"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User
from app.models.user_session import UserSession


class RefreshTokenRejected(ValueError):
    """刷新令牌无效、过期或已被使用。"""


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def hash_refresh_token(raw_token: str) -> str:
    """刷新令牌高熵且只保存 SHA-256，数据库泄漏时不能直接重放。"""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def _access_token(session_id: UUID, user_id: UUID) -> str:
    return create_access_token(
        subject=str(user_id),
        extra_claims={"sid": str(session_id)},
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    )


def token_payload(
    session: UserSession,
    raw_refresh_token: str,
) -> dict:
    """返回登录、注册和刷新接口共用的令牌响应。"""

    return {
        "access_token": _access_token(session.id, session.user_id),
        "refresh_token": raw_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "session_id": str(session.id),
    }


async def create_user_session(
    db: AsyncSession,
    user: User,
    *,
    device_name: str | None = None,
    platform: str | None = None,
    client_version: str | None = None,
) -> dict:
    """登录成功后创建独立设备会话。"""

    raw_refresh, refresh_hash = _new_refresh_token()
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        device_name=(device_name or "")[:120] or None,
        platform=(platform or "")[:40] or None,
        client_version=(client_version or "")[:40] or None,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    await db.flush()
    return token_payload(session, raw_refresh)


async def validate_user_session(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
) -> UserSession | None:
    """每次访问校验会话，使撤销能立即生效。"""

    now = datetime.now(timezone.utc)
    return (
        await db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
    ).scalar_one_or_none()


async def rotate_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
) -> dict:
    """原子轮换刷新令牌；重复使用旧令牌会撤销整个会话。"""

    digest = hash_refresh_token(raw_refresh_token)
    now = datetime.now(timezone.utc)
    session = (
        await db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == digest
            )
        )
    ).scalar_one_or_none()
    if session is None:
        replayed = (
            await db.execute(
                select(UserSession).where(
                    UserSession.previous_refresh_token_hash == digest
                )
            )
        ).scalar_one_or_none()
        if replayed is not None and replayed.revoked_at is None:
            replayed.revoked_at = now
            replayed.revoke_reason = "refresh_replay"
            await db.flush()
        raise RefreshTokenRejected("刷新令牌已失效，请重新登录")

    if session.revoked_at is not None or _utc(session.expires_at) <= now:
        raise RefreshTokenRejected("刷新令牌已过期，请重新登录")
    user = await db.get(User, session.user_id)
    if user is None or user.deleted_at is not None:
        session.revoked_at = now
        session.revoke_reason = "user_inactive"
        await db.flush()
        raise RefreshTokenRejected("账号不可用，请重新登录")

    new_raw, new_hash = _new_refresh_token()
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.id == session.id,
            UserSession.refresh_token_hash == digest,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .values(
            previous_refresh_token_hash=digest,
            refresh_token_hash=new_hash,
            last_used_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.revoked_at = now
        session.revoke_reason = "refresh_race"
        await db.flush()
        raise RefreshTokenRejected("刷新令牌已被使用，请重新登录")
    await db.flush()
    await db.refresh(session)
    return token_payload(session, new_raw)


async def revoke_session(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
    reason: str,
) -> bool:
    session = (
        await db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if session is None:
        return False
    session.revoked_at = datetime.now(timezone.utc)
    session.revoke_reason = reason[:80]
    await db.flush()
    return True


async def revoke_all_sessions(
    db: AsyncSession,
    *,
    user_id: UUID,
    reason: str,
) -> int:
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(
            revoked_at=datetime.now(timezone.utc),
            revoke_reason=reason[:80],
        )
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    return max(0, result.rowcount or 0)


async def list_active_sessions(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> list[UserSession]:
    now = datetime.now(timezone.utc)
    return list(
        (
            await db.execute(
                select(UserSession)
                .where(
                    UserSession.user_id == user_id,
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                )
                .order_by(
                    UserSession.last_used_at.desc(),
                    UserSession.created_at.desc(),
                )
            )
        ).scalars().all()
    )
