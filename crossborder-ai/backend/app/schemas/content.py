"""内容生成接口的请求与响应数据结构。

VeyaShip - Content Generation Schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ContentGenerateRequest(BaseModel):
    """Request to generate AI content for a listing."""
    listing_id: Optional[int] = Field(None, description="Existing listing ID to regenerate content for")
    product_id: Optional[int] = Field(None, description="Product ID to generate listing content from")

    # --- Input ---
    source_text: Optional[str] = Field(None, description="Raw product description / source material")
    source_image_url: Optional[str] = None
    title: Optional[str] = Field(None, description="Product title if known")

    # --- Generation Config ---
    content_type: str = Field(
        default="product_description",
        description="Type: product_title, product_description, bullet_points, seo_title, seo_description, translation, optimization"
    )
    platform: str = Field(
        default="amazon",
        description="Target platform for tone optimization"
    )
    target_language: Optional[str] = Field(
        None, description="Target language code for translation"
    )
    template_id: Optional[int] = Field(None, description="Template override")

    # --- Parameters ---
    tone: Optional[str] = Field(None, description="professional, casual, luxury, etc.")
    target_audience: Optional[str] = None
    keywords: Optional[List[str]] = Field(None, description="Keywords to include")
    max_length: Optional[int] = Field(None, description="Max output length in chars")

    # --- Image Generation ---
    generate_image: bool = Field(default=False, description="Also generate product image via FLUX")
    image_prompt: Optional[str] = Field(None, description="Custom image prompt override")


class ContentGenerateResponse(BaseModel):
    """Response from a content generation request."""
    id: int
    content_type: str
    status: str

    # --- Generated Content ---
    generated_text: Optional[str] = None
    generated_image_url: Optional[str] = None

    # --- AI Info ---
    model_used: str
    tokens_used: Optional[int] = None
    credits_cost: Optional[int] = None

    # --- Suggestions ---
    suggestions: Optional[List[Dict[str, Any]]] = None
    seo_score: Optional[float] = None  # 0-100 estimated SEO score

    created_at: datetime

    model_config = {"from_attributes": True}


class ContentTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    content_type: str
    platform: Optional[str] = None
    language: str
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    is_system: bool
    is_active: bool
    usage_count: int
    avg_rating: Optional[float] = None

    model_config = {"from_attributes": True}


class ContentHistoryResponse(BaseModel):
    items: List[ContentGenerateResponse]
    total: int
    page: int
    page_size: int
