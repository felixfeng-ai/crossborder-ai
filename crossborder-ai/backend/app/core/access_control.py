"""VeyaShip AI - 套餐功能权限控制

每个功能对应一个 feature key，根据用户套餐判断是否有权限。
白名单用户（测试账号）不受套餐限制。
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_config import SystemConfig
from app.models.user import User

# ── 功能权限配置 ──────────────────────────────────────────────
# 每个功能允许的套餐列表
FEATURE_ACCESS: dict[str, list[str]] = {
    "ai_generate": ["free", "standard", "professional"],     # 所有套餐可用（但 free 有次数限制）
    "ai_image": ["professional"],                             # 仅专业版
    "ai_video": ["professional"],                             # 视频生成成本较高，仅专业版
    "shopify_publish": ["standard", "professional"],          # Standard 起可用
    "agent": ["standard", "professional"],                    # Standard 起可用
    "batch_ai": ["standard", "professional"],                 # Standard 起可用
    "category_analysis": ["free", "standard", "professional"],# 所有套餐可用（选品决策核心功能）
}

# ── 白名单（测试账号邮箱，不受限制） ──────────────────────────
WHITELIST_CONFIG_KEY = "access_whitelist_emails"
DEFAULT_WHITELIST_EMAILS: frozenset[str] = frozenset({
    "admin@veyaship.com",  # 平台管理员
    "test@veyaship.com",   # 测试账号
})
WHITELIST_EMAILS: set[str] = set(DEFAULT_WHITELIST_EMAILS)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _replace_cache(emails: set[str]) -> None:
    """原地更新缓存，兼容模块内已经持有的集合引用。"""
    WHITELIST_EMAILS.clear()
    WHITELIST_EMAILS.update(emails)


async def refresh(db: AsyncSession) -> set[str]:
    """从 SystemConfig 加载白名单，供多 Worker 周期同步。"""
    row = (
        await db.execute(
            select(SystemConfig)
            .where(SystemConfig.key == WHITELIST_CONFIG_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    emails = set(DEFAULT_WHITELIST_EMAILS)
    if row is not None:
        try:
            payload = json.loads(row.value or "[]")
            if isinstance(payload, list):
                emails = {
                    normalized
                    for item in payload
                    if isinstance(item, str)
                    and (normalized := _normalize_email(item))
                }
        except json.JSONDecodeError:
            # 配置损坏时回退默认名单，避免把管理员锁在系统外。
            emails = set(DEFAULT_WHITELIST_EMAILS)
    _replace_cache(emails)
    return emails


async def _persist(db: AsyncSession, emails: set[str]) -> None:
    payload = json.dumps(sorted(emails), ensure_ascii=False)
    row = (
        await db.execute(
            select(SystemConfig)
            .where(SystemConfig.key == WHITELIST_CONFIG_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(key=WHITELIST_CONFIG_KEY, value=payload))
    else:
        row.value = payload
    await db.flush()


async def add_whitelist(db: AsyncSession, email: str) -> None:
    """添加白名单账号并持久化到平台配置。"""
    normalized = _normalize_email(email)
    next_emails = set(WHITELIST_EMAILS)
    next_emails.add(normalized)
    await _persist(db, next_emails)
    _replace_cache(next_emails)


async def remove_whitelist(db: AsyncSession, email: str) -> None:
    """移除白名单账号并持久化到平台配置。"""
    normalized = _normalize_email(email)
    next_emails = set(WHITELIST_EMAILS)
    next_emails.discard(normalized)
    await _persist(db, next_emails)
    _replace_cache(next_emails)


def is_whitelisted(user: User) -> bool:
    """判断用户是否在白名单中"""
    return user.email.lower() in WHITELIST_EMAILS


def check_feature_access(user: User, feature: str) -> bool:
    """检查用户是否有权使用某功能

    Args:
        user: 当前用户
        feature: 功能名称（FEATURE_ACCESS 的 key）

    Returns:
        True = 允许使用, False = 无权使用
    """
    # 白名单用户不限
    if is_whitelisted(user):
        return True

    # 检查套餐权限
    allowed_plans = FEATURE_ACCESS.get(feature, [])
    if not allowed_plans:
        return True  # 未配置限制的默认允许

    return user.plan in allowed_plans
