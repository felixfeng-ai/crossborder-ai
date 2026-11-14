"""管理员反馈收件箱。"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import require_admin
from app.models.feedback import FeedbackTicket
from app.models.user import User
from app.routers.feedback import _ticket_response
from app.services.admin_audit import record_admin_action


router = APIRouter(prefix="/admin/feedback", tags=["管理员反馈"])


class FeedbackUpdate(BaseModel):
    """管理员更新反馈状态。"""

    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assigned_to: str | None = Field(None, max_length=255)
    note: str | None = Field(None, max_length=5000)


@router.get("")
async def list_feedback(
    status: str = "",
    type: str = "",
    q: str = Query("", max_length=100),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员按状态、类型和关键词筛选反馈。"""
    query = select(FeedbackTicket)
    if status in {"open", "in_progress", "resolved", "closed"}:
        query = query.where(FeedbackTicket.status == status)
    if type in {"bug", "feature", "billing", "content", "performance", "other"}:
        query = query.where(FeedbackTicket.type == type)
    if q:
        query = query.where(
            or_(
                FeedbackTicket.title.ilike(f"%{q}%"),
                FeedbackTicket.content.ilike(f"%{q}%"),
            )
        )
    rows = (
        await db.execute(query.order_by(desc(FeedbackTicket.created_at)).limit(200))
    ).scalars().all()
    return {"items": [_ticket_response(item) for item in rows]}


@router.patch("/{ticket_id}")
async def update_feedback(
    ticket_id: str,
    payload: FeedbackUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新反馈优先级、负责人和处理状态，并写审计日志。"""
    try:
        ticket_uuid = UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的反馈 ID")
    ticket = await db.get(FeedbackTicket, ticket_uuid)
    if ticket is None:
        raise HTTPException(status_code=404, detail="反馈不存在")

    before = {
        "status": ticket.status,
        "priority": ticket.priority,
        "assigned_to": ticket.assigned_to,
        "note": ticket.note,
    }
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(ticket, key, value)
    ticket.updated_at = datetime.now(timezone.utc)
    if ticket.status in {"resolved", "closed"} and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(timezone.utc)
    if ticket.status in {"open", "in_progress"}:
        ticket.resolved_at = None

    after = {
        "status": ticket.status,
        "priority": ticket.priority,
        "assigned_to": ticket.assigned_to,
        "note": ticket.note,
    }
    await record_admin_action(
        db,
        admin,
        action="feedback.update",
        target_type="feedback",
        target_id=str(ticket.id),
        changes={"before": before, "after": after},
    )
    await db.commit()
    await db.refresh(ticket)
    return _ticket_response(ticket)
