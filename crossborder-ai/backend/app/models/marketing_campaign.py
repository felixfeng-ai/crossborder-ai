"""营销活动：统一承载目标、商品、预算和后续素材。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="conversion",
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="tiktok",
    )
    market: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="US",
    )
    language: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="en",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="planning",
        server_default="planning",
        index=True,
    )
    budget_credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    spent_credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    brief_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
