"""商品图片素材模型。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImageAsset(Base):
    """用户上传或平台处理后的图片素材。"""

    __tablename__ = "image_assets"
    __table_args__ = (
        UniqueConstraint(
            "generation_task_id",
            "variant_index",
            name="uq_image_assets_generation_variant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 移动端素材必须绑定工作区；历史网页素材允许为空以保持向后兼容。
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # upload / processed / generated
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    # product / scene / photography / other：素材库筛选用的真实分类。
    # 默认 other —— 未归类就如实显示未归类，不按 kind 猜一个分类给用户看。
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="other",
        server_default="other",
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    preset_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    background_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # AI 生成图保留来源任务与变体序号，保证自动入库可幂等重试。
    generation_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_generation_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    variant_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        index=True,
    )
    # 软删除避免正在被 Listing 引用的图片因素材库操作立即失效。
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
