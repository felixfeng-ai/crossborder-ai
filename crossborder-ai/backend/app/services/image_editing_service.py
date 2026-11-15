"""图片编辑任务创建与 Provider 能力校验。"""

import json
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.services.image_provider import get_image_provider
from app.services.image_quality import (
    estimate_image_cost_micros,
    image_generation_credits,
)


ImageEditOperation = Literal[
    "inpaint",
    "outpaint",
    "remove_object",
    "upscale",
]

_MASK_REQUIRED = {"inpaint", "remove_object"}
_DEFAULT_PROMPTS = {
    "inpaint": "局部重绘，保持周围画面和商品细节自然连续",
    "outpaint": "自然扩展画面边界，保持商品、光线和构图一致",
    "remove_object": "移除蒙版中的物体，补全背景，保持光影自然",
    "upscale": "图片高清放大，保持原始内容和品牌细节",
}
_EDIT_PROVIDERS = {
    "inpaint": "replicate",
    "outpaint": "replicate",
    "remove_object": "replicate",
    "upscale": "local",
}


async def create_image_edit_task(
    db: AsyncSession,
    user: User,
    *,
    source_asset_id: str,
    operation: ImageEditOperation,
    mask_asset_id: str | None,
    prompt: str,
    aspect_ratio: str,
    scale: int,
    idempotency_key: str | None,
) -> ImageGenerationTask:
    """验证源图、蒙版和 Provider 后创建持久编辑任务。"""
    if not check_feature_access(user, "ai_image"):
        raise PermissionError("图片生成功能仅限专业版套餐使用")
    if idempotency_key:
        existing = (
            await db.execute(
                select(ImageGenerationTask).where(
                    ImageGenerationTask.user_id == user.id,
                    ImageGenerationTask.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    source = await _get_owned_asset(db, user.id, source_asset_id)
    if source is None:
        raise ValueError("源素材不存在")
    mask = None
    if mask_asset_id:
        mask = await _get_owned_asset(db, user.id, mask_asset_id)
        if mask is None:
            raise ValueError("蒙版素材不存在")
    if operation in _MASK_REQUIRED and mask is None:
        raise ValueError("局部编辑必须提供蒙版素材")

    provider_name = _EDIT_PROVIDERS[operation]
    provider = get_image_provider(provider_name)
    if not provider.supports(operation, "standard"):
        raise ValueError("图片编辑服务暂未配置，请管理员检查 Replicate 编辑模型")

    credits_cost = image_generation_credits(operation, "standard", 1)
    if user.credits < credits_cost:
        raise ValueError(f"积分不足，本次图片编辑需要 {credits_cost} 积分")

    safe_scale = 2 if scale not in {2, 4} else scale
    target_width = source.width * (safe_scale if operation == "upscale" else 1)
    target_height = source.height * (safe_scale if operation == "upscale" else 1)
    if target_width > 6000 or target_height > 6000:
        raise ValueError("放大后的图片尺寸过大，请降低倍率")
    reference_ids = [str(source.id)]
    if mask is not None:
        reference_ids.append(str(mask.id))

    resolved_prompt = prompt.strip() or _DEFAULT_PROMPTS[operation]
    task = ImageGenerationTask(
        user_id=user.id,
        prompt=resolved_prompt,
        mode=operation,
        quality_tier=None,
        provider=provider_name,
        resolution=f"{target_width}x{target_height}",
        aspect_ratio=aspect_ratio or _aspect_ratio(source.width, source.height),
        negative_prompt="变形、模糊、错误 Logo、错误包装文字、水印",
        style_preset="image_edit",
        use_brand_persona=False,
        reference_assets_json=json.dumps(reference_ids, ensure_ascii=False),
        reference_coverage="provided",
        generation_params_json=json.dumps(
            {
                "operation": operation,
                "source_asset_id": str(source.id),
                "mask_asset_id": str(mask.id) if mask is not None else None,
                "scale": safe_scale if operation == "upscale" else 1,
            },
            ensure_ascii=False,
        ),
        estimated_cost_micros=estimate_image_cost_micros(
            operation,
            "standard",
            1,
        ),
        idempotency_key=idempotency_key,
        num_outputs=1,
        credits_cost=credits_cost,
        credits_charged=0,
        status="pending",
        attempts=0,
        image_urls="[]",
        model_used="",
        error=None,
    )
    db.add(task)
    await db.flush()
    return task


async def _get_owned_asset(
    db: AsyncSession,
    user_id,
    raw_asset_id: str,
) -> ImageAsset | None:
    try:
        asset_id = uuid.UUID(str(raw_asset_id))
    except (TypeError, ValueError):
        return None
    return (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def _aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "1:1"
    ratio = width / height
    candidates = {
        "1:1": 1.0,
        "4:5": 0.8,
        "3:4": 0.75,
        "16:9": 16 / 9,
        "9:16": 9 / 16,
    }
    return min(candidates, key=lambda key: abs(candidates[key] - ratio))
