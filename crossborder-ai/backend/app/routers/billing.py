"""VeyaShip AI - 套餐与支付路由

当前收款方式：人工转账 + 管理员审核（可运营闭环）。
用户提交升级申请（选套餐 + 留联系方式 + 得到订单号）→ 转账 →
账单页看到"待确认"状态 → 管理员核对后一键开通套餐 / 拒绝。

管理员端（require_admin，邮箱在 ADMIN_EMAILS 里）：
- GET  /billing/admin/upgrades        待办 + 历史对账
- POST /billing/upgrades/{id}/approve  核对转账后开通套餐
- POST /billing/upgrades/{id}/reject   拒绝（留原因）
"""

import uuid as uuid_lib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.credit_purchase import CreditPurchase
from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.user import User
from app.services.credit_service import apply_monthly_allowance
from app.services.plan_service import (
    CREDIT_PACKS,
    PLAN_CATALOG,
    activate_paid_plan,
    get_active_subscription,
    get_or_create_wallet,
    grant_purchased_credits,
    plan_wallet_response,
)

router = APIRouter(prefix="/billing", tags=["套餐与支付"])

PLANS = [
    {
        "id": plan,
        "name": config["name"],
        "price": config["price"],
        "price_label": "免费" if config["price"] == 0 else f"¥{config['price']}/月",
        "description": (
            "试试基本功能"
            if plan == "free"
            else "适合个人卖家"
            if plan == "standard"
            else "适合工作室与专业卖家"
        ),
        "features": [
            f"每月 {config['monthly_credits']} AI 积分",
            *( ["1688 商品抓取", "利润计算器", "合规审查"] if plan == "free" else []),
            *( ["AI 智能助手", "批量生成与 Shopify 发布", "全部 11 个平台"] if plan == "standard" else []),
            *( ["所有 Standard 功能", "AI 图片与视频生成", "优先技术支持"] if plan == "professional" else []),
        ],
        "validity_days": config["valid_days"],
        "recommended": plan == "standard",
    }
    for plan, config in PLAN_CATALOG.items()
]


class UpgradeRequest(BaseModel):
    plan: str = Field(..., description="目标套餐: standard, professional")
    contact: str = Field(..., min_length=2, max_length=100, description="联系方式（微信/手机），付款后通知")


class HandleRequest(BaseModel):
    note: str = Field("", max_length=200, description="管理员备注（拒绝原因等）")


class CreditPackPurchaseRequest(BaseModel):
    pack_id: str
    contact: str = Field(..., min_length=2, max_length=100)


def _request_response(req: PlanUpgradeRequest) -> dict:
    """申请记录转响应结构"""
    return {
        "id": str(req.id),
        "plan": req.plan,
        "contact": req.contact,
        "order_id": req.order_id,
        "amount": req.amount,
        "status": req.status,
        "note": req.note or "",
        "created_at": str(req.created_at) if req.created_at else None,
        "handled_at": str(req.handled_at) if req.handled_at else None,
    }


@router.get("/plans")
async def get_plans():
    return {"plans": PLANS}


@router.get("/wallet")
async def get_wallet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回双钱包、套餐到期时间和当前统计。"""
    await apply_monthly_allowance(db, current_user)
    wallet = await get_or_create_wallet(db, current_user)
    subscription = await get_active_subscription(db, current_user.id)
    return plan_wallet_response(current_user, wallet, subscription)


@router.get("/credit-packs")
async def list_credit_packs():
    return {"packs": list(CREDIT_PACKS)}


def _credit_purchase_response(purchase: CreditPurchase) -> dict:
    return {
        "id": str(purchase.id),
        "pack_id": purchase.pack_id,
        "pack_name": purchase.pack_name,
        "credits": purchase.credits,
        "amount": purchase.amount,
        "order_id": purchase.order_id,
        "contact": purchase.contact,
        "status": purchase.status,
        "note": purchase.note or "",
        "created_at": str(purchase.created_at),
        "handled_at": str(purchase.handled_at) if purchase.handled_at else None,
    }


@router.post("/credit-packs/purchase")
async def purchase_credit_pack(
    payload: CreditPackPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pack = next((item for item in CREDIT_PACKS if item["id"] == payload.pack_id), None)
    if pack is None:
        raise HTTPException(status_code=400, detail="积分包不存在")
    existing = (
        await db.execute(
            select(CreditPurchase).where(
                CreditPurchase.user_id == current_user.id,
                CreditPurchase.pack_id == payload.pack_id,
                CreditPurchase.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            **_credit_purchase_response(existing),
            "message": "该积分包已有待确认订单",
        }
    order_id = f"CP{datetime.now():%Y%m%d}{uuid_lib.uuid4().hex[:8].upper()}"
    purchase = CreditPurchase(
        user_id=current_user.id,
        pack_id=pack["id"],
        pack_name=pack["name"],
        credits=pack["credits"],
        amount=pack["price"],
        order_id=order_id,
        contact=payload.contact,
        status="pending",
    )
    db.add(purchase)
    await db.commit()
    return {
        **_credit_purchase_response(purchase),
        "message": f"订单已创建，请付款 ¥{pack['price']} 并备注订单号 {order_id}",
    }


@router.get("/credit-packs/purchases")
async def list_my_credit_purchases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    purchases = (
        await db.execute(
            select(CreditPurchase)
            .where(CreditPurchase.user_id == current_user.id)
            .order_by(desc(CreditPurchase.created_at))
            .limit(100)
        )
    ).scalars().all()
    return {"items": [_credit_purchase_response(item) for item in purchases]}


@router.get("/admin/credit-packs")
async def list_all_credit_purchases(
    status: str = "",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(CreditPurchase)
    if status in {"pending", "approved", "rejected"}:
        query = query.where(CreditPurchase.status == status)
    purchases = (
        await db.execute(query.order_by(desc(CreditPurchase.created_at)).limit(200))
    ).scalars().all()
    return {"items": [_credit_purchase_response(item) for item in purchases]}


@router.post("/credit-packs/{purchase_id}/approve")
async def approve_credit_purchase(
    purchase_id: str,
    payload: HandleRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    purchase = await _load_pending_credit_purchase(db, purchase_id)
    user = (await db.execute(select(User).where(User.id == purchase.user_id))).scalar_one()
    await grant_purchased_credits(
        db,
        user,
        purchase.credits,
        reference_type="credit_purchase",
        reference_id=purchase.order_id,
    )
    purchase.status = "approved"
    purchase.handled_by = admin.id
    purchase.handled_at = datetime.now(timezone.utc)
    purchase.note = payload.note or "已确认收款，积分包已到账"
    await db.commit()
    return {"ok": True, **_credit_purchase_response(purchase)}


@router.post("/credit-packs/{purchase_id}/reject")
async def reject_credit_purchase(
    purchase_id: str,
    payload: HandleRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    purchase = await _load_pending_credit_purchase(db, purchase_id)
    purchase.status = "rejected"
    purchase.handled_by = admin.id
    purchase.handled_at = datetime.now(timezone.utc)
    purchase.note = payload.note or "未收到转账，积分包订单已拒绝"
    await db.commit()
    return {"ok": True, **_credit_purchase_response(purchase)}


@router.post("/upgrade")
async def upgrade_plan(
    payload: UpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交升级申请（人工收款：转账后管理员审核开通）

    申请落库为一条 plan_upgrade_requests 记录，用户可在
    GET /billing/upgrades 查看处理状态。
    """
    if payload.plan not in ["standard", "professional"]:
        raise HTTPException(status_code=400, detail="无效的套餐")

    # 同一套餐已有待处理申请 → 直接返回，避免重复提交刷单
    existing = (await db.execute(
        select(PlanUpgradeRequest).where(
            PlanUpgradeRequest.user_id == current_user.id,
            PlanUpgradeRequest.plan == payload.plan,
            PlanUpgradeRequest.status == "pending",
        )
    )).scalar_one_or_none()
    if existing:
        return {
            **_request_response(existing),
            "message": "你已有待处理的升级申请，客服确认转账后即开通",
        }

    plan_info = next((p for p in PLANS if p["id"] == payload.plan), None)
    amount = plan_info["price"] if plan_info else 0
    order_id = f"VS{datetime.now():%Y%m%d}{uuid_lib.uuid4().hex[:8].upper()}"

    req = PlanUpgradeRequest(
        user_id=current_user.id,
        plan=payload.plan,
        contact=payload.contact,
        order_id=order_id,
        amount=amount,
        status="pending",
    )
    db.add(req)
    await db.commit()

    return {
        **_request_response(req),
        "message": (
            f"升级申请已提交，请转账 ¥{amount} 到以下账户，备注订单号 {order_id}，"
            "客服核对到账后即为你开通。"
        ),
        "account": {
            "type": "支付宝 / 微信",
            "note": "请添加客服微信手动处理",
        },
    }


@router.get("/upgrades")
async def list_my_upgrades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看自己的升级申请记录（含处理状态）"""
    result = await db.execute(
        select(PlanUpgradeRequest)
        .where(PlanUpgradeRequest.user_id == current_user.id)
        .order_by(desc(PlanUpgradeRequest.created_at))
    )
    return {"items": [_request_response(r) for r in result.scalars().all()]}


# ── 管理员端（人工收款审核）────────────────────────────────────
@router.get("/admin/upgrades")
async def list_all_upgrades(
    status: str = "",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员对账：所有升级申请，最新在前。?status=pending 只看待办。"""
    query = select(PlanUpgradeRequest)
    if status in ("pending", "approved", "rejected"):
        query = query.where(PlanUpgradeRequest.status == status)
    result = await db.execute(query.order_by(desc(PlanUpgradeRequest.created_at)).limit(200))
    return {"items": [_request_response(r) for r in result.scalars().all()]}


@router.post("/upgrades/{request_id}/approve")
async def approve_upgrade(
    request_id: str,
    payload: HandleRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员核对转账后开通套餐：改 plan + 加积分 + 标记已处理"""
    req = await _load_pending_request(db, request_id)

    user = (await db.execute(select(User).where(User.id == req.user_id))).scalar_one()
    await activate_paid_plan(db, user, req.plan)

    req.status = "approved"
    req.handled_by = admin.id
    req.handled_at = datetime.now(timezone.utc)
    req.note = payload.note or "已确认收款，开通套餐"
    await db.commit()

    return {"ok": True, **_request_response(req)}


async def _load_pending_credit_purchase(
    db: AsyncSession,
    purchase_id: str,
) -> CreditPurchase:
    from uuid import UUID
    try:
        pid = UUID(purchase_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的积分包订单 ID")
    purchase = (
        await db.execute(select(CreditPurchase).where(CreditPurchase.id == pid))
    ).scalar_one_or_none()
    if purchase is None:
        raise HTTPException(status_code=404, detail="积分包订单不存在")
    if purchase.status != "pending":
        raise HTTPException(status_code=400, detail="该积分包订单已处理")
    return purchase


@router.post("/upgrades/{request_id}/reject")
async def reject_upgrade(
    request_id: str,
    payload: HandleRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员拒绝升级申请（如未收到转账）"""
    req = await _load_pending_request(db, request_id)
    req.status = "rejected"
    req.handled_by = admin.id
    req.handled_at = datetime.now(timezone.utc)
    req.note = payload.note or "未收到转账，申请已拒绝"
    await db.commit()

    return {"ok": True, **_request_response(req)}


async def _load_pending_request(db: AsyncSession, request_id: str) -> PlanUpgradeRequest:
    """加载待处理申请，校验存在且未处理。"""
    from uuid import UUID
    try:
        rid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的申请ID")

    req = (await db.execute(
        select(PlanUpgradeRequest).where(PlanUpgradeRequest.id == rid)
    )).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理，不能重复操作")
    return req
