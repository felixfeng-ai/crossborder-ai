"""VeyaShip - Subscription & Payment Models.

Subscription plans and payment invoices via Creem.io.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    EXPIRED = "expired"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"


class BillingInterval(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Subscription(Base):
    """User subscription plan."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Plan ---
    plan_name: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # starter / professional / enterprise
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.TRIALING
    )
    billing_interval: Mapped[BillingInterval] = mapped_column(
        Enum(BillingInterval), default=BillingInterval.MONTHLY
    )

    # --- Pricing ---
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")

    # --- Creem.io ---
    creem_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    creem_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    creem_product_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # --- Period ---
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canceled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Credits ---
    credits_per_period: Mapped[int] = mapped_column(Integer, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)

    # --- Features ---
    features_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON granted feature flags

    # --- Metadata ---
    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- Relationships ---
    # 旧支付接口仍在使用该模型；不声明反向属性，避免 User 未加载时污染全局 mapper。
    user = relationship("User")
    invoices = relationship(
        "PaymentInvoice", back_populates="subscription", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.id}: {self.plan_name} [{self.status.value}]>"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentInvoice(Base):
    """Payment invoice record from Creem.io."""

    __tablename__ = "payment_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Creem.io ---
    creem_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    creem_payment_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # --- Payment Info ---
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # --- Billing ---
    billing_reason: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # subscription_create / subscription_cycle / manual
    plan_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Receipt ---
    receipt_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    invoice_pdf_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ---
    subscription = relationship("Subscription", back_populates="invoices")

    def __repr__(self) -> str:
        return f"<PaymentInvoice {self.id}: ${self.amount} [{self.status.value}]>"
