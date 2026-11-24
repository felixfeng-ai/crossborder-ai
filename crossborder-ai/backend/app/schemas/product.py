"""商品接口的请求与响应数据结构。

VeyaShip - Product Schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    title: str = Field(..., max_length=500, description="Product title")
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    price: float = Field(default=0.0, ge=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    image_url: Optional[str] = None
    additional_images: Optional[List[str]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    weight: Optional[float] = None
    weight_unit: str = "kg"


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=100)
    price: Optional[float] = Field(None, ge=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    image_url: Optional[str] = None
    additional_images: Optional[List[str]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    description: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    compare_at_price: Optional[float] = None
    cost_price: Optional[float] = None
    stock_quantity: int
    is_active: bool
    image_url: Optional[str] = None
    additional_images: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    shopify_product_id: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
