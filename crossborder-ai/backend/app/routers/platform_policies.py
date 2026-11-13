"""平台政策知识库管理和检索 API。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.policy_knowledge import PolicySource
from app.models.user import User
from app.services.policy_knowledge import (
    ingest_policy_text,
    search_policy_knowledge,
)


router = APIRouter(prefix="/platform-policies", tags=["Platform Policies"])


class PolicyIngestRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    platform: str = Field(..., min_length=2, max_length=30)
    market: str = Field("US", min_length=2, max_length=20)
    category: str | None = Field(None, max_length=50)
    document_type: str = Field("listing_policy", max_length=50)
    source_url: str = Field(..., min_length=8)
    version: str = Field(..., min_length=1, max_length=80)
    effective_at: datetime | None = None
    content_text: str = Field(..., min_length=20)


@router.post("/ingest", status_code=201)
async def ingest_platform_policy(
    payload: PolicyIngestRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员导入或更新一份全局平台政策。"""
    return await ingest_policy_text(
        db,
        title=payload.title,
        platform=payload.platform,
        market=payload.market,
        category=payload.category,
        document_type=payload.document_type,
        source_url=payload.source_url,
        version=payload.version,
        effective_at=payload.effective_at,
        content_text=payload.content_text,
    )


@router.get("/search")
async def search_platform_policies(
    query: str = Query(..., min_length=2),
    platform: str | None = Query(None),
    market: str | None = Query(None),
    category: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=10),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """检索当前平台已启用的政策原文。"""
    return await search_policy_knowledge(
        db,
        query=query,
        platform=platform,
        market=market,
        category=category,
        top_k=top_k,
    )


@router.get("/sources")
async def list_policy_sources(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员查看政策来源和同步状态。"""
    rows = (
        await db.execute(
            select(PolicySource)
            .order_by(desc(PolicySource.updated_at))
            .limit(200)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "platform": item.platform,
                "market": item.market,
                "category": item.category,
                "document_type": item.document_type,
                "source_url": item.source_url,
                "version": item.version,
                "effective_at": (
                    item.effective_at.isoformat()
                    if item.effective_at
                    else None
                ),
                "status": item.status,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in rows
        ],
        "total": len(rows),
    }
