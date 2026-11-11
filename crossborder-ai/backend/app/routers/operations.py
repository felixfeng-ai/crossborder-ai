"""运营监控、补货计划与预警接口。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.monitor_setting import MonitorSetting
from app.models.operation_alert import OperationAlert
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.models.variant_snapshot import VariantSnapshot
from app.core.rate_limit import RateLimit
from app.services.operations_monitor import (
    get_or_create_settings,
    refresh_supplier_costs,
    run_monitor_scan,
    serialize_alert,
    serialize_settings,
)


router = APIRouter(prefix="/operations", tags=["Operations Monitor"])


class MonitorSettingsRequest(BaseModel):
    target_margin_rate: float = Field(25, ge=0, le=100)
    low_stock_days: int = Field(7, ge=1, le=365)
    lead_time_days: int = Field(14, ge=1, le=365)
    safety_stock_days: int = Field(3, ge=0, le=365)
    platform_fee_rate: float = Field(0.15, ge=0, le=1)
    shipping_cost: float = Field(0, ge=0)
    cost_increase_alert_rate: float = Field(8, ge=0, le=1000)


class SalesRateRequest(BaseModel):
    daily_sales_rate: float = Field(..., ge=0, le=100000)


class AlertUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(acknowledged|open)$")


@router.get("/settings")
async def get_monitor_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    setting = await get_or_create_settings(db, current_user.id)
    return serialize_settings(setting)


@router.put("/settings")
async def update_monitor_settings(
    payload: MonitorSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    setting = await get_or_create_settings(db, current_user.id)
    for field, value in payload.model_dump().items():
        setattr(setting, field, value)
    await db.flush()
    await db.refresh(setting)
    return serialize_settings(setting)


@router.post("/scan")
async def scan_operations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await run_monitor_scan(db, current_user)


@router.post("/refresh-costs")
async def refresh_supplier_cost_snapshots(
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    return await refresh_supplier_costs(db, current_user)


@router.get("/overview")
async def get_operations_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    setting = await get_or_create_settings(db, current_user.id)
    open_alerts = (
        await db.execute(
            select(func.count(OperationAlert.id)).where(
                OperationAlert.user_id == current_user.id,
                OperationAlert.status == "open",
            )
        )
    ).scalar() or 0
    latest_snapshot = (
        await db.execute(
            select(VariantSnapshot)
            .where(VariantSnapshot.user_id == current_user.id)
            .order_by(desc(VariantSnapshot.captured_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "settings": serialize_settings(setting),
        "open_alerts": open_alerts,
        "last_scanned_at": str(latest_snapshot.captured_at) if latest_snapshot else None,
    }


@router.get("/alerts")
async def list_operation_alerts(
    alert_status: Optional[str] = Query(
        "open",
        alias="status",
        pattern="^(open|acknowledged|resolved|all)$",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(OperationAlert).where(OperationAlert.user_id == current_user.id)
    if alert_status != "all":
        query = query.where(OperationAlert.status == alert_status)
    result = await db.execute(
        query.order_by(
            desc(OperationAlert.created_at),
            desc(OperationAlert.id),
        ).limit(500)
    )
    items = result.scalars().all()
    return {"items": [serialize_alert(item) for item in items], "total": len(items)}


@router.patch("/alerts/{alert_id}")
async def update_operation_alert(
    alert_id: str,
    payload: AlertUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed_id = UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="预警不存在")
    alert = (
        await db.execute(
            select(OperationAlert).where(
                OperationAlert.id == parsed_id,
                OperationAlert.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="预警不存在")
    alert.status = payload.status
    alert.acknowledged_at = (
        datetime.now(timezone.utc)
        if payload.status == "acknowledged"
        else None
    )
    await db.flush()
    await db.refresh(alert)
    return serialize_alert(alert)


@router.patch("/variants/{variant_id}/sales-rate")
async def update_variant_sales_rate(
    variant_id: str,
    payload: SalesRateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed_id = UUID(variant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="变体不存在")
    variant = (
        await db.execute(
            select(ProductVariant).where(
                ProductVariant.id == parsed_id,
                ProductVariant.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if variant is None:
        raise HTTPException(status_code=404, detail="变体不存在")
    variant.daily_sales_rate = payload.daily_sales_rate
    await db.flush()
    await db.refresh(variant)
    return {
        "variant_id": str(variant.id),
        "sku": variant.sku,
        "daily_sales_rate": variant.daily_sales_rate,
    }
