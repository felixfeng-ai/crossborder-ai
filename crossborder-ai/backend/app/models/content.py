"""VeyaShip - Content Generation & Template Models.

Tracks AI-generated content and reusable prompt templates.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ContentType(str, enum.Enum):
    PRODUCT_TITLE = "product_title"
    PRODUCT_DESCRIPTION = "product_description"
    BULLET_POINTS = "bullet_points"
    SEO_TITLE = "seo_title"
    SEO_DESCRIPTION = "seo_description"
    SOCIAL_MEDIA_POST = "social_media_post"
    AD_COPY = "ad_copy"
    EMAIL_MARKETING = "email_marketing"
    BLOG_POST = "blog_post"
    IMAGE_PROMPT = "image_prompt"
    TRANSLATION = "translation"
    OPTIMIZATION = "optimization"


class ContentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentGeneration(Base):
    """Record of a single AI content generation request and its result."""

    __tablename__ = "content_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("listings.id", ondelete="SET NULL"), nullable=True
    )

    # --- Generation Info ---
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType), nullable=False
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus), default=ContentStatus.PENDING, nullable=False
    )
    source_language: Mapped[str] = mapped_column(String(20), default="en")
    target_language: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # For translations

    # --- Source ---
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_image_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )

    # --- Result ---
    generated_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_image_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )

    # --- AI Metadata ---
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_parameters: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    credits_cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Feedback ---
    user_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    user_edited: Mapped[bool] = mapped_column(default=False)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Error ---
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships ---
    # 保留生成记录到用户的正向关系，但不要求 User 模型声明反向集合。
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ContentGeneration {self.id}: {self.content_type.value} [{self.status.value}]>"


class ContentTemplate(Base):
    """Reusable prompt templates for content generation."""

    __tablename__ = "content_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType), nullable=False
    )
    platform: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # Target platform
    language: Mapped[str] = mapped_column(String(20), default="en")

    # --- Template ---
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_prompt_template: Mapped[Text] = mapped_column(Text, nullable=False)
    parameters_schema: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON schema for expected params

    # --- Tone & Style ---
    tone: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # professional, casual, luxury, etc.
    target_audience: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Metadata ---
    is_system: Mapped[bool] = mapped_column(default=False)  # Built-in template
    is_active: Mapped[bool] = mapped_column(default=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[Optional[float]] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ContentTemplate {self.id}: {self.name} ({self.content_type.value})>"
