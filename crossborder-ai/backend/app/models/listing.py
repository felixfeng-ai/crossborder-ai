"""VeyaShip - Listing & ListingVariant Models.

Multi-platform product listings with AI-generated content.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ListingPlatform(str, enum.Enum):
    SHOPIFY = "shopify"
    AMAZON = "amazon"
    EBAY = "ebay"
    ETSY = "etsy"
    WALMART = "walmart"
    ALIEXPRESS = "aliexpress"
    SHOPEE = "shopee"
    LAZADA = "lazada"
    MANUAL = "manual"


class ListingStatus(str, enum.Enum):
    DRAFT = "draft"
    AI_GENERATED = "ai_generated"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    FAILED = "failed"


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Platform ---
    platform: Mapped[ListingPlatform] = mapped_column(
        Enum(ListingPlatform), nullable=False
    )
    platform_listing_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # ID on the external platform
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus), default=ListingStatus.DRAFT, nullable=False
    )

    # --- Listing Content ---
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bullet_points: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array
    search_terms: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array
    seo_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Pricing ---
    price: Mapped[float] = mapped_column(Float, default=0.0)
    sale_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")

    # --- Media ---
    main_image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    additional_image_urls: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array

    # --- AI Metadata ---
    ai_generated: Mapped[bool] = mapped_column(default=False)
    ai_model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ai_prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ---
    # 旧 Listing 模型只保留正向关系；反向集合统一由新的 ListingDraft 承担。
    owner = relationship("User")
    product = relationship("Product")
    variants = relationship(
        "ListingVariant", back_populates="listing", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Listing {self.id}: {self.title} [{self.platform.value}]>"


class ListingVariant(Base):
    """Variants for a listing (size, color, etc.)."""

    __tablename__ = "listing_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )

    option1_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    option1_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option2_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    option2_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    option3_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    option3_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- Relationships ---
    listing = relationship("Listing", back_populates="variants")

    def __repr__(self) -> str:
        return f"<ListingVariant {self.id}: {self.option1_value}>"
