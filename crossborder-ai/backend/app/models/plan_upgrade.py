"""VeyaShip - 套餐升级申请模型

人工收款闭环：用户提交升级申请（选套餐 + 留联系方式 + 得到订单号），
转账后在账单页看到申请状态；管理员在管理页看到待办列表，
核对转账后一键开通套餐 / 拒绝，形成可追溯的对账单。

状态机：pending → approved | rejected
"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlanUpgradeRequest(Base):
    """套餐升级申请 —— 每条申请一行，管理员处理后可追溯"""

    __tablename__ = "plan_upgrade_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 目标套餐：standard / professional
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    # 联系方式（微信 / 手机号），用于付款后通知
    contact: Mapped[str] = mapped_column(String(100), nullable=False)
    # 订单号（用户转账时备注）
    order_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    # 应付金额（人民币）
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 日常价，用于审计活动实际减免
    original_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # monthly / annual
    billing_cycle: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )
    # 活动标识，如 new_customer_first_month / annual_10_for_12
    promotion_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 活动额外赠送的购买积分
    bonus_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 本次开通的有效天数
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # pending / approved / rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # 管理员处理备注（拒绝原因等）
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 处理人（管理员用户 ID）
    handled_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
