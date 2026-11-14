"""管理员套餐与积分包版本管理。"""

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import require_admin
from app.models.plan_version import CreditPackVersion, PlanVersion
from app.models.user import User
from app.services.admin_audit import record_admin_action


router = APIRouter(prefix="/admin", tags=["管理员套餐"])


class PlanVersionCreate(BaseModel):
    """管理员创建套餐草稿版本。"""

    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=300)
    rank: int = Field(..., ge=0, le=100)
    price_cents: int = Field(..., ge=0)
    first_month_price_cents: int = Field(0, ge=0)
    annual_price_cents: int = Field(0, ge=0)
    annual_full_price_cents: int = Field(0, ge=0)
    monthly_credits: int = Field(..., ge=0)
    first_month_bonus_credits: int = Field(0, ge=0)
    valid_days: int = Field(..., ge=0, le=3650)
    features: list[str] = Field(default_factory=list)


class CreditPackVersionCreate(BaseModel):
    """管理员创建积分包草稿版本。"""

    name: str = Field(..., min_length=1, max_length=100)
    credits: int = Field(..., ge=1)
    price_cents: int = Field(..., ge=0)
    trial_once: bool = False


def _plan_version_response(row: PlanVersion) -> dict:
    """返回管理端完整版本数据。"""
    try:
        features = json.loads(row.features_json or "[]")
    except json.JSONDecodeError:
        features = []
    return {
        "id": str(row.id),
        "plan_key": row.plan_key,
        "version": row.version,
        "name": row.name,
        "description": row.description,
        "rank": row.rank,
        "price_cents": row.price_cents,
        "first_month_price_cents": row.first_month_price_cents,
        "annual_price_cents": row.annual_price_cents,
        "annual_full_price_cents": row.annual_full_price_cents,
        "monthly_credits": row.monthly_credits,
        "first_month_bonus_credits": row.first_month_bonus_credits,
        "valid_days": row.valid_days,
        "features": features,
        "status": row.status,
        "effective_at": str(row.effective_at) if row.effective_at else None,
        "created_at": str(row.created_at),
    }


def _credit_pack_response(row: CreditPackVersion) -> dict:
    """返回管理端积分包版本。"""
    return {
        "id": str(row.id),
        "pack_key": row.pack_key,
        "version": row.version,
        "name": row.name,
        "credits": row.credits,
        "price_cents": row.price_cents,
        "trial_once": row.trial_once,
        "status": row.status,
        "effective_at": str(row.effective_at) if row.effective_at else None,
        "created_at": str(row.created_at),
    }


@router.get("/catalog")
async def get_catalog(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回套餐和积分包的全部版本，最新在前。"""
    plans = (
        await db.execute(
            select(PlanVersion).order_by(
                PlanVersion.plan_key, desc(PlanVersion.version)
            )
        )
    ).scalars().all()
    packs = (
        await db.execute(
            select(CreditPackVersion).order_by(
                CreditPackVersion.pack_key, desc(CreditPackVersion.version)
            )
        )
    ).scalars().all()
    return {
        "plans": [_plan_version_response(row) for row in plans],
        "credit_packs": [_credit_pack_response(row) for row in packs],
    }


@router.post("/plans/{plan_key}/versions")
async def create_plan_version(
    plan_key: str,
    payload: PlanVersionCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """基于当前套餐创建下一版草稿。"""
    if plan_key not in {"free", "standard", "professional"}:
        raise HTTPException(status_code=400, detail="不支持新增套餐标识")
    latest_version = await db.scalar(
        select(func.max(PlanVersion.version)).where(PlanVersion.plan_key == plan_key)
    ) or 0
    row = PlanVersion(
        plan_key=plan_key,
        version=int(latest_version) + 1,
        name=payload.name,
        description=payload.description,
        rank=payload.rank,
        price_cents=payload.price_cents,
        first_month_price_cents=payload.first_month_price_cents or payload.price_cents,
        annual_price_cents=payload.annual_price_cents or payload.price_cents * 12,
        annual_full_price_cents=(
            payload.annual_full_price_cents or payload.price_cents * 12
        ),
        monthly_credits=payload.monthly_credits,
        first_month_bonus_credits=payload.first_month_bonus_credits,
        valid_days=payload.valid_days,
        features_json=json.dumps(payload.features, ensure_ascii=False),
        status="draft",
        created_by=admin.id,
    )
    db.add(row)
    await db.flush()
    await record_admin_action(
        db,
        admin,
        action="plan.version.create",
        target_type="plan",
        target_id=plan_key,
        changes={"version": row.version, "payload": payload.model_dump()},
    )
    await db.commit()
    await db.refresh(row)
    return _plan_version_response(row)


@router.post("/plan-versions/{version_id}/publish")
async def publish_plan_version(
    version_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """发布套餐草稿并归档同套餐旧版本。"""
    row = await _load_plan_version(db, version_id)
    if row.status == "published":
        raise HTTPException(status_code=409, detail="该版本已经发布")
    await db.execute(
        update(PlanVersion)
        .where(
            PlanVersion.plan_key == row.plan_key,
            PlanVersion.status == "published",
        )
        .values(status="archived")
    )
    row.status = "published"
    row.effective_at = datetime.now(timezone.utc)
    await record_admin_action(
        db,
        admin,
        action="plan.version.publish",
        target_type="plan",
        target_id=row.plan_key,
        changes={"version": row.version, "price_cents": row.price_cents},
    )
    await db.commit()
    await db.refresh(row)
    return _plan_version_response(row)


@router.post("/plan-versions/{version_id}/archive")
async def archive_plan_version(
    version_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """归档套餐版本。"""
    row = await _load_plan_version(db, version_id)
    row.status = "archived"
    await record_admin_action(
        db,
        admin,
        action="plan.version.archive",
        target_type="plan",
        target_id=row.plan_key,
        changes={"version": row.version},
    )
    await db.commit()
    await db.refresh(row)
    return _plan_version_response(row)


@router.post("/credit-packs/{pack_key}/versions")
async def create_credit_pack_version(
    pack_key: str,
    payload: CreditPackVersionCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建积分包草稿。"""
    latest_version = await db.scalar(
        select(func.max(CreditPackVersion.version)).where(
            CreditPackVersion.pack_key == pack_key
        )
    ) or 0
    row = CreditPackVersion(
        pack_key=pack_key,
        version=int(latest_version) + 1,
        name=payload.name,
        credits=payload.credits,
        price_cents=payload.price_cents,
        trial_once=payload.trial_once,
        status="draft",
        created_by=admin.id,
    )
    db.add(row)
    await db.flush()
    await record_admin_action(
        db,
        admin,
        action="credit_pack.version.create",
        target_type="credit_pack",
        target_id=pack_key,
        changes={"version": row.version, "payload": payload.model_dump()},
    )
    await db.commit()
    await db.refresh(row)
    return _credit_pack_response(row)


@router.post("/credit-pack-versions/{version_id}/publish")
async def publish_credit_pack_version(
    version_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """发布积分包草稿，归档同积分包旧版本。"""
    try:
        version_uuid = UUID(version_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的积分包版本 ID")
    row = await db.get(CreditPackVersion, version_uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="积分包版本不存在")
    await db.execute(
        update(CreditPackVersion)
        .where(
            CreditPackVersion.pack_key == row.pack_key,
            CreditPackVersion.status == "published",
        )
        .values(status="archived")
    )
    row.status = "published"
    row.effective_at = datetime.now(timezone.utc)
    await record_admin_action(
        db,
        admin,
        action="credit_pack.version.publish",
        target_type="credit_pack",
        target_id=row.pack_key,
        changes={"version": row.version, "price_cents": row.price_cents},
    )
    await db.commit()
    await db.refresh(row)
    return _credit_pack_response(row)


async def _load_plan_version(db: AsyncSession, version_id: str) -> PlanVersion:
    """加载套餐版本并给出稳定错误。"""
    try:
        version_uuid = UUID(version_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的套餐版本 ID")
    row = await db.get(PlanVersion, version_uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="套餐版本不存在")
    return row
