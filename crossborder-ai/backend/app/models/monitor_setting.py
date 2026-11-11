"""用户级运营监控阈值设置。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MonitorSetting(Base):
    __tablename__ = "monitor_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_margin_rate: Mapped[float] = mapped_column(Float, default=25.0, nullable=False)
    low_stock_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    safety_stock_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    platform_fee_rate: Mapped[float] = mapped_column(Float, default=0.15, nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_increase_alert_rate: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
