"""v1 AI 内容生成接口。

VeyaShip - AI Content Generation Endpoints.

Generate, list, and manage AI-generated listing content via DeepSeek."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, PaginationParams
from app.models.user import User
from app.models.content import ContentGeneration, ContentTemplate, ContentType, ContentStatus
from app.schemas.content import (
    ContentGenerateRequest,
    ContentGenerateResponse,
    ContentHistoryResponse,
    ContentTemplateResponse,
)

router = APIRouter(prefix="/content", tags=["Content Generation"])


@router.post("/generate", response_model=ContentGenerateResponse)
async def generate_content(
    payload: ContentGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI content for a product listing using DeepSeek.

    Creates a content generation record and triggers the AI service.
    The actual generation happens asynchronously — poll the returned ID for status updates.
    """
    # Credit check
    if current_user.credits_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. Please upgrade your plan.",
        )

    # Create generation record
    generation = ContentGeneration(
        user_id=current_user.id,
        listing_id=payload.listing_id,
        content_type=payload.content_type,
        status=ContentStatus.PENDING,
        source_text=payload.source_text,
        source_image_url=payload.source_image_url,
        target_language=payload.target_language,
        model_used=settings.DEEPSEEK_MODEL,
        creds_cost=1,
    )
    db.add(generation)
    await db.flush()

    # NOTE: Actual AI call will be dispatched via background task / Celery.
    # For now, the record is created and will be processed asynchronously.

    return ContentGenerateResponse(
        id=generation.id,
        content_type=generation.content_type.value,
        status=generation.status.value,
        model_used=generation.model_used,
        credits_cost=1,
        created_at=generation.created_at,
    )


@router.get("/history", response_model=ContentHistoryResponse)
async def list_content_history(
    content_type: Optional[ContentType] = Query(None, description="Filter by type"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's content generation history."""
    query = select(ContentGeneration).where(
        ContentGeneration.user_id == current_user.id
    )

    if content_type:
        query = query.where(ContentGeneration.content_type == content_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    query = query.order_by(ContentGeneration.created_at.desc())
    query = query.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return ContentHistoryResponse(
        items=[ContentGenerateResponse.model_validate(g) for g in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/history/{generation_id}", response_model=ContentGenerateResponse)
async def get_generation_detail(
    generation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific content generation."""
    result = await db.execute(
        select(ContentGeneration).where(
            ContentGeneration.id == generation_id,
            ContentGeneration.user_id == current_user.id,
        )
    )
    generation = result.scalar_one_or_none()
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


# --- Templates ---
@router.get("/templates", response_model=list[ContentTemplateResponse])
async def list_templates(
    content_type: Optional[ContentType] = Query(None, description="Filter by type"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    db: AsyncSession = Depends(get_db),
):
    """List available content generation templates."""
    query = select(ContentTemplate).where(ContentTemplate.is_active == True)

    if content_type:
        query = query.where(ContentTemplate.content_type == content_type)
    if platform:
        query = query.where(ContentTemplate.platform == platform)

    query = query.order_by(ContentTemplate.is_system.desc(), ContentTemplate.usage_count.desc())
    result = await db.execute(query)
    return result.scalars().all()
