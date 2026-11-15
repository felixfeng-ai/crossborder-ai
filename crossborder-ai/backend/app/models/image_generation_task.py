"""VeyaShip - AI 图片生成任务模型（CAP-07 落库）"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImageGenerationTask(Base):
    """图片生成任务表 —— 每个图片生成请求一行记录

    状态、重试信息和结果均写 DB。调度器从该表抢占任务，进程重启后仍可恢复。
    """

    __tablename__ = "image_generation_tasks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_image_generation_tasks_user_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 空值表示素材来自普通工作台；有值时必须归属当前营销活动。
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    # 新请求记录生成模式；升级前存量任务统一回填为 legacy。
    mode: Mapped[str] = mapped_column(
        String(32),
        default="legacy",
        server_default="legacy",
        nullable=False,
        index=True,
    )
    quality_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider: Mapped[str] = mapped_column(
        String(24),
        default="auto",
        server_default="auto",
        nullable=False,
    )
    resolution: Mapped[str | None] = mapped_column(String(24), nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(12), nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_preset: Mapped[str | None] = mapped_column(String(80), nullable=True)
    use_brand_persona: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    # 参考图只存素材 UUID；文件仍由 image_assets 统一鉴权和清理。
    reference_assets_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        server_default="[]",
        nullable=False,
    )
    reference_coverage: Mapped[str] = mapped_column(
        String(24),
        default="none",
        server_default="none",
        nullable=False,
    )
    generation_params_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        server_default="{}",
        nullable=False,
    )
    estimated_cost_micros: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    actual_cost_micros: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    # 同一用户重复提交同一个幂等键时复用任务，避免重复扣费。
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_generation_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    next_poll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
