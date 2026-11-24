"""支付与订阅接口的数据结构。

VeyaShip - Payment & Subscription Schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateCheckoutRequest(BaseModel):
    """Request to create a Creem.io checkout session."""
    plan_name: str = Field(..., description="starter / professional / enterprise")
    billing_interval: str = Field(default="monthly", description="monthly / yearly")
    success_url: str = Field(..., description="Redirect URL on success")
    cancel_url: str = Field(..., description="Redirect URL on cancel")


class CreateCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class SubscriptionResponse(BaseModel):
    id: int
    user_id: int
    plan_name: str
    status: str
    billing_interval: str
    amount: float
    currency: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    credits_per_period: int
    credits_used: int
    features: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: int
    subscription_id: Optional[int] = None
    amount: float
    currency: str
    status: str
    payment_method: Optional[str] = None
    billing_reason: Optional[str] = None
    plan_name: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    receipt_url: Optional[str] = None
    invoice_pdf_url: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WebhookResponse(BaseModel):
    success: bool
    message: str = "Webhook processed"


class PlanInfo(BaseModel):
    """Public plan information."""
    name: str
    display_name: str
    description: str
    monthly_price: float
    yearly_price: float
    credits_per_month: int
    features: List[str]


class PlansListResponse(BaseModel):
    plans: List[PlanInfo]
