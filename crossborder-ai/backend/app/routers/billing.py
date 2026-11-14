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
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.credit_purchase import CreditPurchase
from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.subscription import UserSubscription
from app.models.user import User
from app.services.credit_service import apply_monthly_allowance
from app.services.plan_catalog_service import (
    get_plan_rank,
    list_public_credit_packs,
    list_public_plans,
)
from app.services.plan_service import (
    activate_paid_plan,
    get_active_subscription,
    get_or_create_wallet,
    grant_purchased_credits,
    plan_wallet_response,
)

router = APIRouter(prefix="/billing", tags=["套餐与支付"])

CAMPAIGN_CODE = "year_end_2026"
CAMPAIGN_NAME = "2026 年末增长季"
# UTC 时间对应北京时间 2026-11-12 00:00 至 2026-12-01 00:00。
CAMPAIGN_START = datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc)
CAMPAIGN_END = datetime(2026, 11, 30, 16, 0, tzinfo=timezone.utc)
def _now() -> datetime:
    """集中时间源，便于活动资格测试与后续运营配置。"""
    return datetime.now(timezone.utc)


def _campaign_active(now: datetime | None = None) -> bool:
    current = now or _now()
    return CAMPAIGN_START <= current < CAMPAIGN_END

class UpgradeRequest(BaseModel):
    plan: str = Field(..., description="目标套餐: standard, professional")
    contact: str = Field(..., min_length=2, max_length=100, description="联系方式（微信/手机），付款后通知")
    billing_cycle: Literal["monthly", "annual"] = Field(
        "monthly",
        description="计费周期：monthly / annual",
    )


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
        "original_amount": req.original_amount,
        "billing_cycle": req.billing_cycle,
        "promotion_code": req.promotion_code,
        "bonus_credits": req.bonus_credits,
        "duration_days": req.duration_days,
        "status": req.status,
        "note": req.note or "",
        "created_at": str(req.created_at) if req.created_at else None,
        "handled_at": str(req.handled_at) if req.handled_at else None,
    }


@router.get("/plans")
async def get_plans(db: AsyncSession = Depends(get_db)):
    """返回当前最新已发布套餐，数据库缺失时使用代码兜底。"""
    return {"plans": await list_public_plans(db)}


async def _first_month_eligible(db: AsyncSession, user: User) -> bool:
    """只允许从未开通过付费套餐的 Free 用户领取首月价。"""
    if user.plan != "free":
        return False
    had_subscription = await db.scalar(
        select(UserSubscription.id)
        .where(UserSubscription.user_id == user.id)
        .limit(1)
    )
    if had_subscription is not None:
        return False
    had_first_month_request = await db.scalar(
        select(PlanUpgradeRequest.id)
        .where(
            PlanUpgradeRequest.user_id == user.id,
            PlanUpgradeRequest.status.in_(("pending", "approved")),
            PlanUpgradeRequest.promotion_code == "new_customer_first_month",
        )
        .limit(1)
    )
    if had_first_month_request is not None:
        return False
    had_paid_upgrade = await db.scalar(
        select(PlanUpgradeRequest.id)
        .where(
            PlanUpgradeRequest.user_id == user.id,
            PlanUpgradeRequest.status == "approved",
        )
        .limit(1)
    )
    return had_paid_upgrade is None


async def _trial_pack_eligible(db: AsyncSession, user: User) -> bool:
    """待处理订单也占用资格，已成功订单永久占用。"""
    existing = await db.scalar(
        select(CreditPurchase.id)
        .where(
            CreditPurchase.user_id == user.id,
            CreditPurchase.pack_id == "pack_trial_50",
            CreditPurchase.status.in_(("pending", "approved")),
        )
        .limit(1)
    )
    return existing is None


@router.get("/campaign")
async def get_campaign(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    active = _campaign_active()
    first_month_eligible = active and await _first_month_eligible(db, current_user)
    trial_pack_eligible = active and await _trial_pack_eligible(db, current_user)
    return {
        "code": CAMPAIGN_CODE,
        "name": CAMPAIGN_NAME,
        "active": active,
        "starts_at": CAMPAIGN_START.isoformat(),
        "ends_at": CAMPAIGN_END.isoformat(),
        "first_month_eligible": first_month_eligible,
        "trial_pack_eligible": trial_pack_eligible,
        "plans": await list_public_plans(db),
    }


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
async def list_credit_packs(db: AsyncSession = Depends(get_db)):
    """返回当前最新已发布积分包。"""
    return {"packs": await list_public_credit_packs(db)}


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
    packs = await list_public_credit_packs(db)
    pack = next((item for item in packs if item["id"] == payload.pack_id), None)
    if pack is None:
        raise HTTPException(status_code=400, detail="积分包不存在")
    if pack.get("trial_once"):
        approved_trial = await db.scalar(
            select(CreditPurchase.id)
            .where(
                CreditPurchase.user_id == current_user.id,
                CreditPurchase.pack_id == pack["id"],
                CreditPurchase.status == "approved",
            )
            .limit(1)
        )
        if approved_trial is not None:
            raise HTTPException(
                status_code=409,
                detail="首购体验包每个账号只能成功购买一次",
            )
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
    plans = await list_public_plans(db)
    plan_map = {item["id"]: item for item in plans}
    if payload.plan not in plan_map:
        raise HTTPException(status_code=400, detail="无效的套餐")
    target_rank = await get_plan_rank(db, payload.plan)
    current_rank = await get_plan_rank(db, current_user.plan)
    if target_rank <= current_rank:
        raise HTTPException(
            status_code=409,
            detail="只能申请高于当前套餐的计划，当前套餐及低档套餐无需重复申请",
        )

    # 同一套餐已有待处理申请 → 直接返回，避免重复提交刷单
    existing = (await db.execute(
        select(PlanUpgradeRequest).where(
            PlanUpgradeRequest.user_id == current_user.id,
            PlanUpgradeRequest.status == "pending",
        )
    )).scalar_one_or_none()
    if existing:
        return {
            **_request_response(existing),
            "message": "你已有待处理的升级申请，客服确认转账后即开通",
        }

    plan_info = plan_map[payload.plan]

    campaign_active = _campaign_active()
    first_month_eligible = (
        campaign_active
        and payload.billing_cycle == "monthly"
        and await _first_month_eligible(db, current_user)
    )
    if payload.billing_cycle == "annual":
        amount = (
            plan_info["annual_price"]
            if campaign_active
            else plan_info["annual_full_price"]
        )
        original_amount = plan_info["annual_full_price"]
        promotion_code = "annual_10_for_12" if campaign_active else None
        bonus_credits = 0
        duration_days = 365
    elif first_month_eligible:
        amount = plan_info["first_month_price"]
        original_amount = plan_info["price"]
        promotion_code = "new_customer_first_month"
        bonus_credits = int(plan_info["first_month_bonus_credits"])
        duration_days = 30
    else:
        amount = plan_info["price"]
        original_amount = plan_info["price"]
        promotion_code = None
        bonus_credits = 0
        duration_days = 30
    order_id = f"VS{datetime.now():%Y%m%d}{uuid_lib.uuid4().hex[:8].upper()}"

    req = PlanUpgradeRequest(
        user_id=current_user.id,
        plan=payload.plan,
        contact=payload.contact,
        order_id=order_id,
        amount=amount,
        original_amount=original_amount,
        billing_cycle=payload.billing_cycle,
        promotion_code=promotion_code,
        bonus_credits=bonus_credits,
        duration_days=duration_days,
        status="pending",
    )
    db.add(req)
    await db.commit()

    return {
        **_request_response(req),
        "message": (
            f"升级申请已提交，请转账 ¥{amount} 到以下账户，备注订单号 {order_id}，"
            "客服核对到账后即为你开通。"
            + (
                f" 本单另赠 {bonus_credits} 积分。"
                if bonus_credits
                else ""
            )
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
    target_rank = await get_plan_rank(db, req.plan)
    current_rank = await get_plan_rank(db, user.plan)
    if target_rank <= current_rank:
        req.status = "rejected"
        req.handled_by = admin.id
        req.handled_at = datetime.now(timezone.utc)
        req.note = "当前套餐已覆盖该申请，禁止开通低档或同级套餐"
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail="该申请不是有效升级，已自动标记拒绝，不能开通低档或同级套餐",
        )
    await activate_paid_plan(
        db,
        user,
        req.plan,
        duration_days=req.duration_days or 30,
    )
    if req.bonus_credits:
        await grant_purchased_credits(
            db,
            user,
            req.bonus_credits,
            reference_type="plan_upgrade_bonus",
            reference_id=req.order_id,
        )

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
