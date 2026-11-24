"""Listing 接口的请求与响应数据结构。

VeyaShip - Listing Schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ListingVariantResponse(BaseModel):
    id: int
    listing_id: int
    option1_name: Optional[str] = None
    option1_value: Optional[str] = None
    option2_name: Optional[str] = None
    option2_value: Optional[str] = None
    option3_name: Optional[str] = None
    option3_value: Optional[str] = None
    sku: Optional[str] = None
    price: float
    stock_quantity: int
    image_url: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class ListingCreate(BaseModel):
    product_id: Optional[int] = None
    platform: str = Field(..., description="Target platform: shopify, amazon, ebay, etsy, etc.")
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    bullet_points: Optional[List[str]] = None
    search_terms: Optional[List[str]] = None
    price: float = Field(default=0.0, ge=0)
    sale_price: Optional[float] = Field(None, ge=0)
    currency: str = "USD"
    main_image_url: Optional[str] = None
    additional_image_urls: Optional[List[str]] = None


class ListingUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    bullet_points: Optional[List[str]] = None
    search_terms: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    sale_price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    main_image_url: Optional[str] = None
    additional_image_urls: Optional[List[str]] = None
    status: Optional[str] = None


class ListingResponse(BaseModel):
    id: int
    owner_id: int
    product_id: Optional[int] = None
    platform: str
    platform_listing_id: Optional[str] = None
    status: str
    title: str
    description: Optional[str] = None
    bullet_points: Optional[str] = None
    search_terms: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    price: float
    sale_price: Optional[float] = None
    currency: str
    main_image_url: Optional[str] = None
    additional_image_urls: Optional[str] = None
    ai_generated: bool
    ai_model_used: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    variants: List[ListingVariantResponse] = []

    model_config = {"from_attributes": True}


class ListingListResponse(BaseModel):
    items: List[ListingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
