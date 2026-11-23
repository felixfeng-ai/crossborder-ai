"""VeyaShip - 品牌调性模型"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Persona(Base):
    """品牌调性表 —— 每个用户一套品牌配置"""

    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # 品牌信息
    brand_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 调性
    tone: Mapped[str] = mapped_column(String(50), default="professional")
    tone_custom: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 禁词（JSON 数组）
    banned_words: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Brand Kit 扩展字段（CAP-04，均可空）────────────────────
    # 目标市场/站点（如 amazon.com / 美国站 / 日本站）
    target_market: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 主营类目（如 3C 配件 / 家居收纳）
    product_category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 图片风格提示词（如 "clean studio lighting, soft shadows"）
    image_style: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
