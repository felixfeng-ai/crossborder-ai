"""营销多平台图片套图创建、状态聚合与序列化。"""

import json
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_image_suite import (
    MarketingImageSuite,
    MarketingImageSuiteItem,
)
from app.models.user import User
from app.services.image_provider import get_image_provider
from app.services.image_quality import (
    IMAGE_QUALITY_TIERS,
    estimate_image_cost_micros,
    image_generation_credits,
)


MARKETING_SUITE_PLATFORMS: tuple[dict[str, str], ...] = (
    {
        "id": "amazon-main",
        "label": "Amazon 主图",
        "aspect_ratio": "1:1",
    },
    {
        "id": "tiktok-main",
        "label": "TikTok Shop",
        "aspect_ratio": "1:1",
    },
    {
        "id": "shopify-product",
        "label": "Shopify 商品图",
        "aspect_ratio": "1:1",
    },
    {
        "id": "shein-main",
        "label": "SHEIN 商品图",
        "aspect_ratio": "3:4",
    },
    {
        "id": "temu-main",
        "label": "Temu 主图",
        "aspect_ratio": "1:1",
    },
)

_PLATFORM_BY_ID = {
    item["id"]: item
    for item in MARKETING_SUITE_PLATFORMS
}

_DIRECTION_PROMPTS = {
    "conversion": "以高转化为目标，突出商品卖点和清晰购买理由",
    "lifestyle": "把商品放入真实使用场景，保持生活方式自然可信",
    "campaign": "以营销活动为主，画面有明确的节日或活动氛围",
    "premium": "以高级品牌质感为主，克制构图、精细光线和材质表现",
}


def normalize_suite_platforms(platform_ids: list[str]) -> list[dict[str, str]]:
    """去重并校验套图平台，至少保留两个不同平台。"""
    normalized_ids = list(dict.fromkeys(
        str(item).strip() for item in platform_ids if str(item).strip()
    ))
    if len(normalized_ids) < 2:
        raise ValueError("营销套图至少选择两个平台")
    unknown = [item for item in normalized_ids if item not in _PLATFORM_BY_ID]
    if unknown:
        raise ValueError(f"未知平台：{', '.join(unknown)}")
    return [_PLATFORM_BY_ID[item] for item in normalized_ids]


def build_marketing_suite_prompt(
    *,
    title: str,
    direction: str,
    theme: str,
    platform_label: str,
    note: str = "",
) -> str:
    """组装跨平台一致的提示词，只让平台构图要求发生必要变化。"""
    direction_text = _DIRECTION_PROMPTS.get(
        direction,
        _DIRECTION_PROMPTS["conversion"],
    )
    parts = [
        f"为{platform_label}生成跨境电商营销图片",
        f"活动主题：{title}",
        direction_text,
        "严格保持参考商品的外观、材质、Logo、包装文字和颜色一致",
        "商业摄影质感，主体清晰，可直接投放",
    ]
    if theme.strip():
        parts.append(f"视觉氛围：{theme.strip()}")
    if note.strip():
        parts.append(f"补充要求：{note.strip()}")
    return "。".join(parts)


def estimate_marketing_suite_credits(
    platform_ids: list[str],
    quality_tier: str,
) -> int:
    platforms = normalize_suite_platforms(platform_ids)
    unit = image_generation_credits("product_scene", quality_tier, 1)
    return unit * len(platforms)


async def create_marketing_image_suite(
    db: AsyncSession,
    user: User,
    *,
    campaign_id: str,
    title: str,
    direction: str,
    theme: str,
    platform_ids: list[str],
    reference_asset_ids: list[str],
    quality_tier: str,
    note: str,
    idempotency_key: str | None,
    workspace_id: uuid.UUID | None = None,
    include_legacy_workspace: bool = False,
) -> MarketingImageSuite:
    """创建套图主记录和平台任务；任何校验失败都不留下半套任务。"""
    if not check_feature_access(user, "ai_image"):
        raise PermissionError("图片生成功能仅限专业版套餐使用")
    if quality_tier not in IMAGE_QUALITY_TIERS:
        raise ValueError("未知的图片质量档位")

    if idempotency_key:
        suite_query = select(MarketingImageSuite).where(
            MarketingImageSuite.user_id == user.id,
            MarketingImageSuite.idempotency_key == idempotency_key,
        )
        if workspace_id is not None:
            suite_query = suite_query.where(
                MarketingImageSuite.workspace_id == workspace_id
            )
        existing = (
            await db.execute(
                suite_query
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    try:
        campaign_uuid = uuid.UUID(str(campaign_id))
    except (TypeError, ValueError):
        raise ValueError("营销活动不存在")
    campaign_query = select(MarketingCampaign).where(
        MarketingCampaign.id == campaign_uuid,
        MarketingCampaign.user_id == user.id,
    )
    if workspace_id is not None:
        campaign_scope = MarketingCampaign.workspace_id == workspace_id
        if include_legacy_workspace:
            campaign_scope = or_(
                campaign_scope,
                MarketingCampaign.workspace_id.is_(None),
            )
        campaign_query = campaign_query.where(campaign_scope)
    campaign = (
        await db.execute(
            campaign_query
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise ValueError("营销活动不存在")

    platforms = normalize_suite_platforms(platform_ids)
    reference_ids = list(dict.fromkeys(
        str(item).strip()
        for item in reference_asset_ids
        if str(item).strip()
    ))
    if not 1 <= len(reference_ids) <= 4:
        raise ValueError("商品场景至少需要 1 张参考图，最多 4 张")
    parsed_reference_ids = []
    for raw_id in reference_ids:
        try:
            parsed_reference_ids.append(uuid.UUID(raw_id))
        except ValueError:
            raise ValueError("参考素材不存在")
    reference_query = select(ImageAsset).where(
        ImageAsset.id.in_(parsed_reference_ids),
        ImageAsset.user_id == user.id,
    )
    if workspace_id is not None:
        reference_scope = ImageAsset.workspace_id == workspace_id
        if include_legacy_workspace:
            reference_scope = or_(
                reference_scope,
                ImageAsset.workspace_id.is_(None),
            )
        reference_query = reference_query.where(reference_scope)
    references = (
        await db.execute(
            reference_query
        )
    ).scalars().all()
    if len(references) != len(parsed_reference_ids):
        raise ValueError("参考素材不存在")

    provider = get_image_provider("replicate")
    if not provider.supports("product_scene", quality_tier):
        raise ValueError("商品场景参考图生成服务暂未配置")

    total_credits = image_generation_credits(
        "product_scene",
        quality_tier,
        len(platforms),
    )
    from app.services.personal_billing import get_personal_billing_balance

    if await get_personal_billing_balance(db, user) < total_credits:
        raise ValueError(
            f"积分不足，本次营销套图需要 {total_credits} 积分"
        )

    suite = MarketingImageSuite(
        user_id=user.id,
        workspace_id=workspace_id,
        campaign_id=campaign.id,
        title=title.strip(),
        direction=direction.strip() or "conversion",
        theme=theme.strip(),
        quality_tier=quality_tier,
        status="pending",
        total_credits=total_credits,
        idempotency_key=idempotency_key,
    )
    db.add(suite)
    await db.flush()

    reference_json = json.dumps(reference_ids, ensure_ascii=False)
    for position, platform in enumerate(platforms):
        preset_id = platform["id"]
        from app.services.image_processing import get_platform_preset

        preset = get_platform_preset(preset_id)
        unit_credits = image_generation_credits(
            "product_scene",
            quality_tier,
            1,
        )
        task = ImageGenerationTask(
            user_id=user.id,
            workspace_id=workspace_id,
            campaign_id=campaign.id,
            prompt=build_marketing_suite_prompt(
                title=title,
                direction=direction,
                theme=theme,
                platform_label=platform["label"],
                note=note,
            ),
            num_outputs=1,
            mode="product_scene",
            quality_tier=quality_tier,
            provider="replicate",
            resolution=f"{preset['width']}x{preset['height']}",
            aspect_ratio=platform["aspect_ratio"],
            negative_prompt="变形、错误 Logo、错误包装文字、低清晰度、水印",
            style_preset="marketing_suite",
            use_brand_persona=True,
            reference_assets_json=reference_json,
            reference_coverage="provided",
            generation_params_json=json.dumps(
                {
                    "suite_id": str(suite.id),
                    "position": position,
                    "platform": platform["id"],
                    "platform_label": platform["label"],
                    "preset_id": preset_id,
                    "aspect_ratio": platform["aspect_ratio"],
                },
                ensure_ascii=False,
            ),
            estimated_cost_micros=estimate_image_cost_micros(
                "product_scene",
                quality_tier,
                1,
            ),
            idempotency_key=(
                f"{idempotency_key}:{platform['id']}"
                if idempotency_key
                else None
            ),
            credits_cost=unit_credits,
            credits_charged=0,
            status="pending",
            attempts=0,
            image_urls="[]",
            model_used="",
            error=None,
        )
        db.add(task)
        await db.flush()
        db.add(
            MarketingImageSuiteItem(
                suite_id=suite.id,
                platform=platform["id"],
                preset_id=preset_id,
                aspect_ratio=platform["aspect_ratio"],
                position=position,
                image_task_id=task.id,
            )
        )
    await db.flush()
    return suite


async def serialize_marketing_image_suite(
    db: AsyncSession,
    suite: MarketingImageSuite,
) -> dict[str, Any]:
    """聚合平台任务状态，并把证据返回给活动素材板和结果页。"""
    items = (
        await db.execute(
            select(MarketingImageSuiteItem)
            .where(MarketingImageSuiteItem.suite_id == suite.id)
            .order_by(MarketingImageSuiteItem.position)
        )
    ).scalars().all()
    task_ids = [item.image_task_id for item in items]
    tasks = (
        await db.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.id.in_(task_ids)
            )
        )
    ).scalars().all() if task_ids else []
    task_by_id = {task.id: task for task in tasks}
    statuses = [
        task_by_id[item.image_task_id].status
        for item in items
        if item.image_task_id in task_by_id
    ]
    status = _aggregate_suite_status(statuses)
    if suite.status != status:
        suite.status = status
        await db.flush()

    serialized_items = []
    for item in items:
        task = task_by_id.get(item.image_task_id)
        try:
            image_urls = json.loads(task.image_urls or "[]") if task else []
        except (json.JSONDecodeError, TypeError):
            image_urls = []
        serialized_items.append({
            "id": str(item.id),
            "task_id": str(item.image_task_id),
            "platform": item.platform,
            "platform_label": _PLATFORM_BY_ID.get(
                item.platform,
                {"label": item.platform},
            )["label"],
            "preset_id": item.preset_id,
            "aspect_ratio": item.aspect_ratio,
            "status": task.status if task else "failed",
            "image_urls": image_urls if isinstance(image_urls, list) else [],
            "model_used": task.model_used if task else "",
            "error": task.error if task else "图片任务不存在",
            "credits": (
                task.credits_charged or task.credits_cost
                if task else 0
            ),
        })
    return {
        "suite_id": str(suite.id),
        "campaign_id": str(suite.campaign_id),
        "title": suite.title,
        "direction": suite.direction,
        "theme": suite.theme,
        "quality_tier": suite.quality_tier,
        "status": status,
        "total_credits": suite.total_credits,
        "completed_count": statuses.count("completed"),
        "failed_count": statuses.count("failed"),
        "items": serialized_items,
        "created_at": str(suite.created_at),
        "updated_at": str(suite.updated_at),
    }


def _aggregate_suite_status(statuses: list[str]) -> str:
    if not statuses:
        return "failed"
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status in {"pending", "processing"} for status in statuses):
        return "processing" if any(
            status == "processing" for status in statuses
        ) else "pending"
    if any(status == "completed" for status in statuses):
        return "partial_failed"
    return "failed"
