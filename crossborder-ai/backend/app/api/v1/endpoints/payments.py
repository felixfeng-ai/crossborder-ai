"""VeyaShip - Payment & Subscription Endpoints.

Plan management, Creem.io checkout, webhooks, and billing history.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, PaginationParams
from app.models.user import User
from app.models.payment import Subscription, SubscriptionStatus, PaymentInvoice
from app.services.payment import PaymentService
from app.schemas.payment import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    InvoiceResponse,
    PlanInfo,
    PlansListResponse,
    SubscriptionResponse,
    WebhookResponse,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


# --- Public Plan Info ---
PLANS = [
    PlanInfo(
        name="free",
        display_name="Free",
        description="Get started with basic AI content generation",
        monthly_price=0,
        yearly_price=0,
        credits_per_month=10,
        features=[
            "10 AI content generations/month",
            "Basic listing templates",
            "1 platform export",
            "Standard support",
        ],
    ),
    PlanInfo(
        name="starter",
        display_name="Starter",
        description="For growing cross-border sellers",
        monthly_price=29,
        yearly_price=290,
        credits_per_month=100,
        features=[
            "100 AI content generations/month",
            "Advanced templates & tones",
            "Multi-platform listings",
            "SEO optimization",
            "AI image generation (10/mo)",
            "Shopify integration",
            "Email support",
        ],
    ),
    PlanInfo(
        name="professional",
        display_name="Professional",
        description="For serious e-commerce businesses",
        monthly_price=79,
        yearly_price=790,
        credits_per_month=500,
        features=[
            "500 AI content generations/month",
            "All templates & tones",
            "Bulk generation",
            "AI image generation (50/mo)",
            "RAG knowledge base",
            "Competitor analysis",
            "Translation (10 languages)",
            "Priority support",
        ],
    ),
    PlanInfo(
        name="enterprise",
        display_name="Enterprise",
        description="Custom solutions for large operations",
        monthly_price=199,
        yearly_price=1990,
        credits_per_month=2000,
        features=[
            "2,000 AI content generations/month",
            "Unlimited AI image generation",
            "Custom AI agent workflows",
            "Advanced RAG with Qdrant",
            "API access & webhooks",
            "Dedicated account manager",
            "Custom integrations",
            "SLA guarantee",
        ],
    ),
]


@router.get("/plans", response_model=PlansListResponse)
async def list_plans():
    """List available subscription plans with pricing and features."""
    return PlansListResponse(plans=PLANS)


# --- Subscription ---
@router.get("/subscription", response_model=Optional[SubscriptionResponse])
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's active subscription."""
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.is_active == True,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        return None

    resp = SubscriptionResponse.model_validate(subscription)
    # Parse features JSON
    if subscription.features_json:
        import json
        resp.features = json.loads(subscription.features_json)
    return resp


@router.post("/create-checkout", response_model=CreateCheckoutResponse)
async def create_checkout(
    payload: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a Creem.io checkout session for subscription purchase."""
    # Validate plan
    plan_names = [p.name for p in PLANS]
    if payload.plan_name not in plan_names:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan. Choose from: {', '.join(plan_names)}",
        )

    if payload.billing_interval not in ["monthly", "yearly"]:
        raise HTTPException(status_code=400, detail="Invalid billing interval")

    # NOTE: Actual Creem.io API integration goes here.
    # This creates a checkout session and returns the redirect URL.

    return CreateCheckoutResponse(
        checkout_url=f"https://creem.io/checkout/{payload.plan_name}",
        session_id=f"cs_{current_user.id}_{payload.plan_name}",
    )


@router.post("/webhook", response_model=WebhookResponse)
async def handle_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """处理 Creem.io webhook 事件。"""
    # 必须使用原始字节验签；读取 JSON 后再序列化会改变空白和字段顺序，导致签名失效。
    raw_body = await request.body()
    signature = request.headers.get("creem-signature", "")
    verifier = PaymentService()
    if not await verifier.verify_webhook(raw_body, signature):
        raise HTTPException(status_code=401, detail="Webhook 签名无效")

    try:
        import json

        payload = json.loads(raw_body)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Webhook 请求体格式错误")

    # Creem 当前事件字段为 eventType，同时保留 type 兼容旧版测试数据。
    event_type = payload.get("eventType") or payload.get("type", "")

    if event_type == "payment.succeeded":
        # Update subscription and add credits
        pass
    elif event_type == "subscription.canceled":
        # Mark subscription as canceled
        pass
    elif event_type == "subscription.updated":
        # Sync subscription changes
        pass

    return WebhookResponse(success=True)


# --- Invoices ---
@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's payment invoices."""
    query = (
        select(PaymentInvoice)
        .where(PaymentInvoice.user_id == current_user.id)
        .order_by(PaymentInvoice.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    result = await db.execute(query)
    return result.scalars().all()
