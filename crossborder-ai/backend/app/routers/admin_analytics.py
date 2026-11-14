"""管理员运营分析接口。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.services.admin_analytics import build_admin_analytics_overview


router = APIRouter(prefix="/admin/analytics", tags=["管理员分析"])


@router.get("/overview")
async def get_admin_overview(
    days: int = Query(7, ge=1, le=90),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回业务、流量和性能摘要。"""
    return await build_admin_analytics_overview(db, days=days)
