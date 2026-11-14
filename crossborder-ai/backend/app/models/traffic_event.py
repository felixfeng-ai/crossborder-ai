"""匿名访问与 Web Vitals 原始事件。"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrafficEvent(Base):
    """统一保存页面访问和浏览器性能样本。

    分析表不保存原始 IP 和完整 User-Agent，访问者只使用前端生成的匿名 ID。
    """

    __tablename__ = "traffic_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    referrer_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="unknown")
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    viewport_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(16), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_rating: Mapped[str | None] = mapped_column(String(24), nullable=True)
    release: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
