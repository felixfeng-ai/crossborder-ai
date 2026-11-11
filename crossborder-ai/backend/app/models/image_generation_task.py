"""VeyaShip - AI 图片生成任务模型（CAP-07 落库）"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImageGenerationTask(Base):
    """图片生成任务表 —— 每个图片生成请求一行记录

    状态、重试信息和结果均写 DB。调度器从该表抢占任务，进程重启后仍可恢复。
    """

    __tablename__ = "image_generation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # 使用的图片描述词（已含品牌调性拼接）
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    num_outputs: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    credits_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 状态: pending / processing / completed / failed
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 生成结果图片 URL 列表（JSON 数组文本，参考 persona.banned_words 做法）
    image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 使用的模型（阿里云通义万相 / Replicate FLUX）
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 失败原因（仅 status=failed 时非空）
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
