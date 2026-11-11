"""VeyaShip AI - 套餐功能权限控制

每个功能对应一个 feature key，根据用户套餐判断是否有权限。
白名单用户（测试账号）不受套餐限制。
"""

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
WHITELIST_EMAILS: set[str] = {
    "admin@veyaship.com",  # 平台管理员
    "test@veyaship.com",   # 测试账号
}


def add_whitelist(email: str):
    """添加白名单账号"""
    WHITELIST_EMAILS.add(email.lower())


def remove_whitelist(email: str):
    """移除白名单账号"""
    WHITELIST_EMAILS.discard(email.lower())


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
