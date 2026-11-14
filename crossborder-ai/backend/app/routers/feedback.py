"""用户反馈提交与个人记录。"""

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.feedback import FeedbackTicket
from app.models.user import User


router = APIRouter(prefix="/feedback", tags=["用户反馈"])


class FeedbackCreate(BaseModel):
    """用户提交反馈。"""

    type: Literal["bug", "feature", "billing", "content", "performance", "other"]
    title: str = Field(..., min_length=2, max_length=200)
    content: str = Field(..., min_length=5, max_length=5000)
    page_path: str = Field("", max_length=500)
    page_title: str = Field("", max_length=200)
    browser_info: dict = Field(default_factory=dict)


def _ticket_response(ticket: FeedbackTicket) -> dict:
    """把反馈转成前端稳定契约。"""
    try:
        browser_info = json.loads(ticket.browser_info_json or "{}")
    except json.JSONDecodeError:
        browser_info = {}
    return {
        "id": str(ticket.id),
        "type": ticket.type,
        "title": ticket.title,
        "content": ticket.content,
        "page_path": ticket.page_path,
        "page_title": ticket.page_title,
        "browser_info": browser_info,
        "status": ticket.status,
        "priority": ticket.priority,
        "assigned_to": ticket.assigned_to,
        "note": ticket.note or "",
        "created_at": str(ticket.created_at),
        "updated_at": str(ticket.updated_at),
        "resolved_at": str(ticket.resolved_at) if ticket.resolved_at else None,
    }


@router.post("")
async def create_feedback(
    payload: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存反馈及页面上下文。"""
    now = datetime.now(timezone.utc)
    ticket = FeedbackTicket(
        user_id=current_user.id,
        type=payload.type,
        title=payload.title.strip(),
        content=payload.content.strip(),
        page_path=payload.page_path,
        page_title=payload.page_title,
        browser_info_json=json.dumps(payload.browser_info, ensure_ascii=False)[:8000],
        status="open",
        priority="normal",
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return _ticket_response(ticket)


@router.get("/mine")
async def list_my_feedback(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户的反馈，最新在前。"""
    rows = (
        await db.execute(
            select(FeedbackTicket)
            .where(FeedbackTicket.user_id == current_user.id)
            .order_by(desc(FeedbackTicket.created_at))
            .limit(100)
        )
    ).scalars().all()
    return {"items": [_ticket_response(item) for item in rows]}
