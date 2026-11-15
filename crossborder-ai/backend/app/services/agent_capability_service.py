"""AI Agent 可调用的图片、视频、营销方案与素材服务。

编排器只负责判断意图和组装工具结果；具体资源归属、任务落库、积分预检与
供应商提交集中在这里，避免 Agent 路由与业务路由出现两套不一致实现。
"""

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services import provider_config
from app.services.ai.persona_kit import (
    build_persona_kit,
    fetch_persona,
    format_persona_block,
    image_style_phrase,
    strip_banned_words,
)
from app.services.image_provider import get_image_provider
from app.services.image_quality import (
    IMAGE_QUALITY_TIERS,
    estimate_image_cost_micros,
    image_generation_credits,
)
from app.services.marketing_video_agent import (
    MARKETING_TEMPLATES,
    PLATFORM_OPTIONS,
    generate_marketing_plan,
)
from app.services.minimax_video import (
    VIDEO_TEMPLATES,
)
from app.services.video_quality import (
    compile_i2va_prompt,
    estimate_quality_credits,
    resolve_quality_tier,
)
from app.services.professional_storyboard import provider_render_duration
from app.services.video_provider import get_video_provider


SUPPORTED_MARKETING_DURATIONS = {15, 20, 30}


async def get_owned_image_asset(
    db: AsyncSession,
    user_id,
    asset_id: str,
) -> Optional[ImageAsset]:
    """按用户读取图片素材，跨账号一律按不存在处理。"""
    try:
        parsed_id = UUID(str(asset_id))
    except (ValueError, TypeError):
        return None
    return (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == parsed_id,
                ImageAsset.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def _parse_image_urls(raw: str | None) -> list[str]:
    """解析图片任务结果，损坏数据返回空列表。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def list_user_materials(
    db: AsyncSession,
    user: User,
    *,
    limit: int = 20,
) -> dict:
    """查询当前用户最近素材，并返回可用于 Agent 摘要的总量。"""
    safe_limit = max(1, min(int(limit or 20), 50))

    asset_total = (
        await db.execute(
            select(func.count()).select_from(ImageAsset).where(
                ImageAsset.user_id == user.id
            )
        )
    ).scalar_one()
    image_task_total = (
        await db.execute(
            select(func.count()).select_from(ImageGenerationTask).where(
                ImageGenerationTask.user_id == user.id,
                ImageGenerationTask.status == "completed",
            )
        )
    ).scalar_one()
    materialized_task_ids = select(ImageAsset.generation_task_id).where(
        ImageAsset.user_id == user.id,
        ImageAsset.kind == "generated",
        ImageAsset.generation_task_id.is_not(None),
    )
    legacy_image_task_total = (
        await db.execute(
            select(func.count()).select_from(ImageGenerationTask).where(
                ImageGenerationTask.user_id == user.id,
                ImageGenerationTask.status == "completed",
                ImageGenerationTask.id.not_in(materialized_task_ids),
            )
        )
    ).scalar_one()
    product_video_total = (
        await db.execute(
            select(func.count()).select_from(VideoGenerationTask).where(
                VideoGenerationTask.user_id == user.id,
                VideoGenerationTask.status == "succeeded",
            )
        )
    ).scalar_one()
    marketing_total = (
        await db.execute(
            select(func.count()).select_from(MarketingVideoProject).where(
                MarketingVideoProject.user_id == user.id
            )
        )
    ).scalar_one()

    assets = (
        await db.execute(
            select(ImageAsset)
            .where(ImageAsset.user_id == user.id)
            .order_by(desc(ImageAsset.created_at), desc(ImageAsset.id))
            .limit(safe_limit)
        )
    ).scalars().all()
    image_tasks = (
        await db.execute(
            select(ImageGenerationTask)
            .where(
                ImageGenerationTask.user_id == user.id,
                ImageGenerationTask.status == "completed",
                ImageGenerationTask.id.not_in(materialized_task_ids),
            )
            .order_by(
                desc(ImageGenerationTask.created_at),
                desc(ImageGenerationTask.id),
            )
            .limit(safe_limit)
        )
    ).scalars().all()
    videos = (
        await db.execute(
            select(VideoGenerationTask)
            .where(
                VideoGenerationTask.user_id == user.id,
                VideoGenerationTask.status == "succeeded",
            )
            .order_by(
                desc(VideoGenerationTask.created_at),
                desc(VideoGenerationTask.id),
            )
            .limit(safe_limit)
        )
    ).scalars().all()
    marketing_projects = (
        await db.execute(
            select(MarketingVideoProject)
            .where(MarketingVideoProject.user_id == user.id)
            .order_by(
                desc(MarketingVideoProject.created_at),
                desc(MarketingVideoProject.id),
            )
            .limit(safe_limit)
        )
    ).scalars().all()

    items: list[dict] = []
    for asset in assets:
        items.append(
            {
                "id": str(asset.id),
                "kind": "image",
                "source": asset.kind,
                "name": asset.name,
                "url": f"{settings.API_V1_PREFIX}/images/assets/{asset.id}/file",
                "created_at": str(asset.created_at),
            }
        )
    for task in image_tasks:
        urls = _parse_image_urls(task.image_urls)
        items.append(
            {
                "id": str(task.id),
                "kind": "image_generation",
                "name": task.prompt[:120],
                "urls": urls,
                "created_at": str(task.created_at),
            }
        )
    for video in videos:
        items.append(
            {
                "id": str(video.id),
                "kind": "product_video",
                "name": video.prompt[:120],
                "duration": video.duration,
                "resolution": video.resolution,
                "created_at": str(video.created_at),
            }
        )
    for project in marketing_projects:
        items.append(
            {
                "id": str(project.id),
                "kind": "marketing_video",
                "name": project.title,
                "status": project.status,
                "created_at": str(project.created_at),
            }
        )

    return {
        "counts": {
            "images": int(asset_total or 0) + int(legacy_image_task_total or 0),
            "image_assets": int(asset_total or 0),
            "generated_images": int(image_task_total or 0),
            "materialized_generated_images": int(image_task_total or 0)
            - int(legacy_image_task_total or 0),
            "product_videos": int(product_video_total or 0),
            "marketing_projects": int(marketing_total or 0),
        },
        "items": items[:safe_limit],
    }


async def schedule_product_image_task(
    db: AsyncSession,
    user: User,
    *,
    prompt: str,
    num_outputs: int = 1,
    campaign_id: str | None = None,
    mode: str = "legacy",
    quality_tier: str | None = None,
    aspect_ratio: str = "1:1",
    negative_prompt: str = "",
    style_preset: str | None = None,
    use_brand_persona: bool | None = None,
    provider: str = "auto",
    reference_asset_ids: list[str] | None = None,
    idempotency_key: str | None = None,
) -> ImageGenerationTask:
    """创建持久图片任务，由调度器异步消费。"""
    if not check_feature_access(user, "ai_image"):
        raise PermissionError("图片生成功能仅限专业版套餐使用")

    if mode == "platform_white":
        raise ValueError("平台白底请在图片工作台按尺寸预设处理")
    if mode not in {"legacy", "free_creation", "product_scene"}:
        raise ValueError("未知的图片生成模式")
    resolved_quality = quality_tier or ("fast" if mode == "legacy" else "standard")
    if resolved_quality not in IMAGE_QUALITY_TIERS:
        raise ValueError("未知的图片质量档位")

    references = await _resolve_agent_image_references(
        db,
        user.id,
        reference_asset_ids or [],
        required=mode == "product_scene",
    )
    provider_name = _resolve_agent_image_provider(
        mode,
        resolved_quality,
        provider,
    )
    credits_cost = image_generation_credits(
        mode,
        resolved_quality,
        num_outputs,
    )
    if user.credits < credits_cost:
        raise ValueError(f"积分不足，本次图片生成需要 {credits_cost} 积分")

    enhanced_prompt = prompt.strip()
    should_use_persona = (
        use_brand_persona
        if use_brand_persona is not None
        else mode != "free_creation"
    )
    if should_use_persona:
        persona = await fetch_persona(db, user.id)
        if persona:
            kit = build_persona_kit(persona)
            enhanced_prompt = strip_banned_words(
                enhanced_prompt,
                kit.get("banned_words") or [],
            )
            style_phrase = image_style_phrase(kit)
            if style_phrase:
                enhanced_prompt = f"{enhanced_prompt}, {style_phrase}"
            if kit.get("brand_name"):
                enhanced_prompt = f"{enhanced_prompt}, {kit['brand_name']} brand identity"

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

    task = ImageGenerationTask(
        user_id=user.id,
        campaign_id=UUID(str(campaign_id)) if campaign_id else None,
        prompt=enhanced_prompt,
        num_outputs=max(1, min(int(num_outputs or 1), 4)),
        mode=mode,
        quality_tier=resolved_quality if mode != "legacy" else None,
        provider=provider_name,
        resolution=IMAGE_QUALITY_TIERS[resolved_quality].resolution,
        aspect_ratio=aspect_ratio,
        negative_prompt=negative_prompt,
        style_preset=style_preset,
        use_brand_persona=should_use_persona,
        reference_assets_json=json.dumps(
            [str(asset.id) for asset in references],
            ensure_ascii=False,
        ),
        reference_coverage="provided" if references else "none",
        generation_params_json=json.dumps(
            {
                "mode": mode,
                "quality_tier": resolved_quality,
                "provider": provider_name,
                "aspect_ratio": aspect_ratio,
            },
            ensure_ascii=False,
        ),
        estimated_cost_micros=estimate_image_cost_micros(
            mode,
            resolved_quality,
            num_outputs,
        ),
        idempotency_key=idempotency_key,
        credits_cost=credits_cost,
        status="pending",
        attempts=0,
        image_urls="[]",
        model_used="",
        error=None,
    )
    db.add(task)
    await db.flush()
    return task


async def _resolve_agent_image_references(
    db: AsyncSession,
    user_id,
    raw_ids: list[str],
    *,
    required: bool,
) -> list[ImageAsset]:
    """按顺序校验 Agent 传入的参考图，全部必须属于当前用户。"""
    ids = list(dict.fromkeys(str(item) for item in raw_ids if str(item).strip()))
    if required and not ids:
        raise ValueError("商品场景至少需要 1 张参考图")
    if len(ids) > 4:
        raise ValueError("商品场景最多支持 4 张参考图")
    assets: list[ImageAsset] = []
    for asset_id in ids:
        asset = await get_owned_image_asset(db, user_id, asset_id)
        if asset is None:
            raise ValueError("参考素材不存在")
        assets.append(asset)
    return assets


def _resolve_agent_image_provider(
    mode: str,
    quality_tier: str,
    requested: str,
) -> str:
    """校验 Provider 能力并返回实际 Provider；商品场景禁止降级。"""
    names = (
        ["replicate"]
        if mode == "product_scene"
        else [requested] if requested in {"aliyun", "replicate"} else ["aliyun", "replicate"]
    )
    for name in names:
        provider = get_image_provider(name)
        if provider.supports(mode, quality_tier):
            return name
    if mode == "product_scene":
        raise ValueError("商品场景参考图生成服务暂未配置")
    raise ValueError("图片生成功能暂未配置")


async def create_product_video_task(
    db: AsyncSession,
    user: User,
    *,
    source_asset_id: str,
    prompt: str = "",
    template_id: str = "clean_product",
    quality_tier: str = "draft",
    style_preset: str = "commerce_showcase",
    model: str = "MiniMax-H3-Lite",
    resolution: str = "480P",
    duration: int = 4,
    ratio: str = "9:16",
    reserve_credits: int = 0,
    campaign_id: str | None = None,
) -> VideoGenerationTask:
    """校验权限、积分和首帧后提交商品图生视频任务。"""
    if not check_feature_access(user, "ai_video"):
        raise PermissionError("AI 视频生成仅限专业版套餐使用")
    if ratio != "9:16":
        raise ValueError("当前仅支持 9:16 商品短视频")

    template = next(
        (item for item in VIDEO_TEMPLATES if item["id"] == template_id),
        None,
    )
    if template is None:
        raise ValueError("视频模板不存在")
    asset = await get_owned_image_asset(db, user.id, source_asset_id)
    if asset is None:
        raise ValueError("商品首帧不存在")

    quality = resolve_quality_tier(quality_tier)
    provider = get_video_provider(str(quality["provider"]))
    if not provider.is_configured():
        raise ValueError("所选 AI 视频服务暂未配置")
    model = str(quality["model"])
    resolution = str(quality["resolution"])
    credits_cost = estimate_quality_credits(quality_tier, duration)
    estimated_cost_micros = provider.estimate_cost_micros(
        model,
        resolution,
        duration,
    )
    locked_user = (
        await db.execute(
            select(User).where(User.id == user.id).with_for_update()
        )
    ).scalar_one()
    reserved = max(0, int(reserve_credits or 0))
    required_credits = credits_cost + reserved
    if locked_user.credits < required_credits:
        reserve_hint = f"并为 Agent 任务预留 {reserved} 积分" if reserved else ""
        raise ValueError(
            f"积分不足，本次视频生成需要 {credits_cost} 积分{reserve_hint}"
        )

    final_prompt = compile_i2va_prompt(
        product_name=asset.name,
        direction=prompt,
        duration=duration,
        style_id=style_preset,
        template_direction=template["prompt_suffix"],
    )
    task = VideoGenerationTask(
        user_id=user.id,
        campaign_id=UUID(str(campaign_id)) if campaign_id else None,
        source_asset_id=UUID(str(source_asset_id)),
        template_id=template_id,
        provider=str(quality["provider"]),
        model=model,
        resolution=resolution,
        quality_tier=quality_tier,
        style_preset=style_preset,
        credits_per_second=int(quality["credits_per_second"]),
        duration=duration,
        ratio=ratio,
        prompt=final_prompt,
        status="queued",
        credits_cost=credits_cost,
        estimated_cost_micros=estimated_cost_micros,
    )
    db.add(task)
    await db.flush()

    # 动态导入便于测试替换供应商提交函数，也避免编排器模块加载时触发外部依赖。
    from app.services.video_task_executor import submit_video_task

    try:
        await submit_video_task(db, task)
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc) or "视频任务提交失败"
        task.finished_at = datetime.now(timezone.utc)
        await db.flush()
        raise ValueError(task.error) from exc

    try:
        await locked_user.deduct_credits(
            db,
            credits_cost,
            feature="ai_video",
            reference_type="video_task",
            reference_id=str(task.id),
            description="Agent 提交商品图生视频",
        )
        task.credits_charged = credits_cost
    except Exception:
        # 供应商已经受理，任务不能因本地扣分异常被撤回；留给运营对账。
        task.error = "视频已提交，但积分扣减失败，请联系管理员"
    await db.flush()
    return task


async def create_marketing_plan_project(
    db: AsyncSession,
    user: User,
    *,
    source_asset_id: str,
    product_name: str,
    idea: str,
    platform: str = "tiktok",
    market: str = "US",
    language: str = "en",
    duration: int = 15,
    template_id: str = "presenter_demo",
    quality_tier: str = "draft",
    style_preset: str = "premium_luxury",
    model: str = "MiniMax-H3-Lite",
    resolution: str = "480P",
    campaign_id: str | None = None,
) -> tuple[MarketingVideoProject, int]:
    """生成营销方案和分镜，不提交视频供应商，也不扣视频积分。"""
    if not check_feature_access(user, "ai_video"):
        raise PermissionError("AI 营销视频仅限专业版套餐使用")
    if duration not in SUPPORTED_MARKETING_DURATIONS:
        raise ValueError("营销视频时长仅支持 15、20、30 秒")
    if not any(item["id"] == platform for item in PLATFORM_OPTIONS):
        raise ValueError("目标平台不支持")
    if not any(item["id"] == template_id for item in MARKETING_TEMPLATES):
        raise ValueError("营销视频模板不存在")
    if await get_owned_image_asset(db, user.id, source_asset_id) is None:
        raise ValueError("商品首帧不存在")

    persona = await fetch_persona(db, user.id)
    brand_context = (
        format_persona_block(build_persona_kit(persona))
        if persona
        else None
    )
    plan = await generate_marketing_plan(
        idea=idea,
        product_name=product_name,
        platform=platform,
        market=market,
        language=language,
        duration=duration,
        template_id=template_id,
        brand_context=brand_context,
    )
    quality = resolve_quality_tier(quality_tier)
    provider = get_video_provider(str(quality["provider"]))
    if not provider.is_configured():
        raise ValueError("所选 AI 视频服务暂未配置")
    model = str(quality["model"])
    resolution = str(quality["resolution"])
    credits = sum(
        estimate_quality_credits(
            quality_tier,
            provider_render_duration(
                model,
                int(item["duration"]),
                provider_name=str(quality["provider"]),
            ),
        )
        for item in plan["shots"]
    )
    project = MarketingVideoProject(
        user_id=user.id,
        campaign_id=UUID(str(campaign_id)) if campaign_id else None,
        source_asset_id=UUID(str(source_asset_id)),
        title=plan["title"],
        product_name=product_name,
        idea=idea,
        platform=platform,
        market=market,
        language=language,
        duration=duration,
        template_id=template_id,
        quality_tier=quality_tier,
        style_preset=style_preset,
        provider=str(quality["provider"]),
        credits_per_second=int(quality["credits_per_second"]),
        model=model,
        resolution=resolution,
        status="brief_ready",
        brief_json=json.dumps(plan, ensure_ascii=False),
        credits_estimated=credits,
    )
    db.add(project)
    await db.flush()
    for index, item in enumerate(plan["shots"]):
        compiled_prompt = compile_i2va_prompt(
            product_name=product_name,
            direction=item["prompt"],
            duration=int(item["duration"]),
            style_id=style_preset,
            previous_title=(
                plan["shots"][index - 1]["title"] if index > 0 else None
            ),
            next_title=(
                plan["shots"][index + 1]["title"]
                if index + 1 < len(plan["shots"])
                else None
            ),
        )
        db.add(
            MarketingVideoShot(
                project_id=project.id,
                position=item["position"],
                title=item["title"],
                purpose=item["purpose"],
                prompt=compiled_prompt,
                source_text=item["prompt"],
                duration=item["duration"],
                status="planned",
            )
        )
    await db.flush()
    return project, credits
