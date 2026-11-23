"""用户公开资料响应构造，避免不同路由返回字段不一致。"""

from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserResponse


def build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        credits=user.credits,
        plan=user.plan,
        created_at=user.created_at,
        avatar_url=user.avatar_url,
        is_admin=user.email.lower()
        in {email.lower() for email in settings.ADMIN_EMAILS},
    )
