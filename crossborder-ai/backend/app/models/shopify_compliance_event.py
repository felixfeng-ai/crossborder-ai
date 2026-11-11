"""Shopify 隐私合规 Webhook 处理审计。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShopifyComplianceEvent(Base):
    """记录 Webhook 投递结果，不保存客户 PII 或完整 payload。"""

    __tablename__ = "shopify_compliance_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    webhook_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    shop_domain: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing", index=True
    )
    action_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
