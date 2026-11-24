"""认证领域服务：密码校验、令牌与用户身份相关逻辑。

VeyaShip - Authentication Service.

Higher-level auth logic: registration, login, OAuth integration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User


class AuthService:
    """Handles user authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str | None = None,
        company_name: str | None = None,
    ) -> User:
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
            full_name=full_name,
            company_name=company_name,
            plan="free",
            credits_total=10,
            credits_remaining=10,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_user_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user
