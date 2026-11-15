"""营销多平台图片套图与平台任务映射。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketingImageSuite(Base):
    """一次营销套图请求，聚合多个平台图片任务。"""

    __tablename__ = "marketing_image_suites"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_marketing_image_suites_user_idempotency",
        ),
    )

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
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketing_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="conversion",
    )
    theme: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        server_default="",
    )
    quality_tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="fast",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="pending",
        index=True,
    )
    total_credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
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


class MarketingImageSuiteItem(Base):
    """套图中的一个平台任务；单平台失败不影响其他子项。"""

    __tablename__ = "marketing_image_suite_items"
    __table_args__ = (
        UniqueConstraint(
            "suite_id",
            "platform",
            name="uq_marketing_image_suite_items_platform",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketing_image_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    preset_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    aspect_ratio: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    image_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
