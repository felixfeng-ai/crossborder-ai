"""管理员审计日志查询。"""

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import require_admin
from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User


router = APIRouter(prefix="/admin/audits", tags=["管理员审计"])


@router.get("")
async def list_audits(
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """返回管理员操作，最新在前。"""
    rows = (
        await db.execute(
            select(AdminAuditLog)
            .order_by(desc(AdminAuditLog.created_at))
            .limit(limit)
        )
    ).scalars().all()
    items = []
    for row in rows:
        try:
            changes = json.loads(row.changes_json or "{}")
        except json.JSONDecodeError:
            changes = {}
        items.append(
            {
                "id": str(row.id),
                "admin_user_id": str(row.admin_user_id) if row.admin_user_id else None,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "changes": changes,
                "created_at": str(row.created_at),
            }
        )
    return {"items": items}
