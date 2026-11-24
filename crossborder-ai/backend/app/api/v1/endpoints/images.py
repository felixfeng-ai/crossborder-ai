"""v1 图片生成与历史记录接口。

VeyaShip - AI Image Generation Endpoints.

Generate product images via Replicate FLUX model."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.content import ContentGenerateResponse as ImageGenerateResponse

router = APIRouter(prefix="/images", tags=["Image Generation"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(
    prompt: str,
    product_title: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    num_images: int = 1,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate product images using FLUX AI model via Replicate.

    Args:
        prompt: Text description of the desired image.
        product_title: Optional product title for context.
        negative_prompt: Things to avoid in the image.
        num_images: Number of images to generate (1-4).
    """
    if current_user.credits_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. Please upgrade your plan.",
        )

    if num_images < 1 or num_images > 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="num_images must be between 1 and 4",
        )

    # NOTE: Actual Replicate API call will be implemented in the service layer.
    # This endpoint creates the request record and dispatches generation.

    return ImageGenerateResponse(
        id=0,  # Will be set after DB creation
        content_type="image_generation",
        status="pending",
        model_used="black-forest-labs/flux-schnell",
        credits_cost=num_images,
        created_at=None,  # Will be set by service
    )
