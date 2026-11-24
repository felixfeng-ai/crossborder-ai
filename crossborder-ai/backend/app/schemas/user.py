"""用户、认证令牌与账户接口的数据结构。

VeyaShip - User Schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    username: Optional[str] = Field(None, min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: Optional[str] = None
    credits: int
    plan: str
    created_at: datetime
    avatar_url: Optional[str] = None
    # 管理员标记：邮箱在 ADMIN_EMAILS 配置里，前端据此显示后台管理入口
    is_admin: bool = False

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    session_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
