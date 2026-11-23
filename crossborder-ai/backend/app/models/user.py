"""VeyaShip - 用户模型

存储用户账号信息，使用 UUID 主键，密码加密存储。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InsufficientCreditsError(ValueError):
    """积分不足异常（ValueError 子类）。

    兼容旧调用方（users.py 用 ``except ValueError`` 捕获 → 400），
    同时在 main.py 注册全局处理器 → 其余调用点统一返回 402。
    """


class User(Base):
    """用户表 —— 存储账号、积分、套餐信息

    一个用户对应数据库里一行记录。
    """

    __tablename__ = "users"  # 数据库中表名

    # ── 主键 ──────────────────────────────────────────────────
    # UUID 主键，自动生成，相比自增 ID 更安全（不会暴露用户数量）
    # uuid4 是随机 UUID，碰撞概率极低
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── 账号信息 ──────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
        # unique=True  → 不能有两个用户用同一个邮箱
        # index=True   → 按邮箱搜索时会很快
    )
    username: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
        # nullable=True → 注册时可以不填用户名，以后补
    )
    avatar_storage_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    avatar_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── 密码 ──────────────────────────────────────────────────
    # 存的是 bcrypt 哈希值，不是明文密码
    # String(255) 是因为 bcrypt 哈希输出约 60 字符
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── 业务字段 ──────────────────────────────────────────────
    # credits（积分）用于消耗式计费，每次 AI 生成/抓取扣 1 分
    credits: Mapped[int] = mapped_column(Integer, default=30)
    credit_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # plan（套餐）控制可用功能范围，free / standard / professional
    plan: Mapped[str] = mapped_column(String(50), default="free")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    deletion_reason: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    # ── 时间戳 ──────────────────────────────────────────────
    # server_default=func.now() 由数据库自动填当前时间，不是 Python 填的
    # 这样即使不同服务器的时钟不一致，也以数据库时间为准
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── 业务方法 ──────────────────────────────────────────────
    # 这个方法不是在数据库层面做的，而是在 Python 层面操作对象，
    # 然后通过 session 同步到数据库

    async def deduct_credits(
        self,
        db: AsyncSession,
        amount: int,
        *,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        feature: str = "unknown",
        reference_type: str | None = None,
        reference_id: str | None = None,
        description: str = "",
    ) -> int:
        """原子扣减积分（带行级锁，防并发扣超）

        场景：用户同时发两个请求，各需扣 1 分，但只剩 1 分。
        不加锁 → 两个请求都判断 "够" → 都扣 → 变成 -1 分
        加锁   → 第二个请求会等到第一个扣完 → 发现不够 → 报错

        Args:
            db: 数据库会话
            amount: 要扣的积分数

        Returns:
            扣完后的剩余积分

        Raises:
            ValueError: 积分不足时抛出
        """
        async with db.begin_nested():
            from app.models.credit_transaction import CreditTransaction
            from app.services.personal_billing import (
                get_or_create_personal_wallet,
                get_personal_workspace,
                sync_legacy_wallet_mirror,
                workspace_wallet_balance,
            )

            # 个人工作区钱包是唯一权威源，旧字段只做兼容镜像。
            personal_workspace = await get_personal_workspace(
                db,
                self,
                workspace_id=workspace_id,
            )

            # 个人工作区存在未结案账务差异时，所有消费入口统一止付。
            if personal_workspace is not None:
                from app.services.workspace_billing_reconciliation import (
                    assert_personal_billing_spending_allowed,
                )

                await assert_personal_billing_spending_allowed(
                    db,
                    workspace_id=personal_workspace.id,
                )

            if personal_workspace is None:
                raise ValueError("个人工作区不存在")
            wallet = await get_or_create_personal_wallet(
                db,
                user=self,
                workspace=personal_workspace,
                lock=True,
            )
            available = workspace_wallet_balance(wallet)
            if available < amount:
                raise InsufficientCreditsError(
                    f"积分不足，需要 {amount}，当前 {available}"
                )

            plan_spend = min(int(wallet.plan_credits or 0), amount)
            purchased_spend = amount - plan_spend
            wallet.plan_credits -= plan_spend
            wallet.purchased_credits -= purchased_spend
            balance_after = workspace_wallet_balance(wallet)
            await sync_legacy_wallet_mirror(
                db,
                user=self,
                wallet=wallet,
            )
            wallet_type = (
                "plan"
                if purchased_spend == 0
                else "purchased"
                if plan_spend == 0
                else "mixed"
            )

            db.add(
                CreditTransaction(
                    user_id=self.id,
                    workspace_id=personal_workspace.id,
                    actor_user_id=actor_user_id or self.id,
                    delta=-amount,
                    balance_after=balance_after,
                    feature=feature,
                    wallet_type=wallet_type,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    description=description or f"扣减 {amount} 积分",
                )
            )
            return balance_after

    def __repr__(self) -> str:
        return f"<User {self.id}: {self.email} ({self.plan}, credits={self.credits})>"

    @property
    def avatar_url(self) -> str | None:
        """头像通过鉴权接口读取，版本参数只负责绕过浏览器缓存。"""
        if not self.avatar_storage_key:
            return None
        version = (
            int(self.avatar_updated_at.timestamp())
            if self.avatar_updated_at
            else 0
        )
        # 用户 ID 进入缓存键，切换账号时不会复用上一个账号的头像。
        return f"/api/v1/users/me/avatar?u={self.id}&v={version}"
