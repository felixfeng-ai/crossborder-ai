"""VeyaShip - 用户模型

存储用户账号信息，使用 UUID 主键，密码加密存储。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, select, update
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
            from app.models.credit_wallet import CreditWallet

            wallet = (
                await db.execute(
                    select(CreditWallet)
                    .where(CreditWallet.user_id == self.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if wallet is None:
                wallet = CreditWallet(
                    user_id=self.id,
                    plan_credits=max(0, int(self.credits or 0)),
                    purchased_credits=0,
                )
                db.add(wallet)
                await db.flush()
            else:
                wallet_total = int(wallet.plan_credits or 0) + int(wallet.purchased_credits or 0)
                mirrored_total = int(self.credits or 0)
                if mirrored_total > wallet_total:
                    # 兼容旧代码直接改 User.credits：额外部分视为购买积分。
                    wallet.purchased_credits += mirrored_total - wallet_total
                elif mirrored_total < wallet_total:
                    # 旧字段被人工下调时，钱包跟随，避免余额镜像继续漂移。
                    reduce = wallet_total - mirrored_total
                    from_plan = min(int(wallet.plan_credits or 0), reduce)
                    wallet.plan_credits -= from_plan
                    wallet.purchased_credits -= reduce - from_plan

            available = int(wallet.plan_credits or 0) + int(wallet.purchased_credits or 0)
            if available < amount:
                raise InsufficientCreditsError(
                    f"积分不足，需要 {amount}，当前 {available}"
                )

            plan_spend = min(int(wallet.plan_credits or 0), amount)
            purchased_spend = amount - plan_spend
            wallet.plan_credits -= plan_spend
            wallet.purchased_credits -= purchased_spend
            self.credits = available - amount
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
                    delta=-amount,
                    balance_after=self.credits,
                    feature=feature,
                    wallet_type=wallet_type,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    description=description or f"扣减 {amount} 积分",
                )
            )
            return self.credits

    def __repr__(self) -> str:
        return f"<User {self.id}: {self.email} ({self.plan}, credits={self.credits})>"
