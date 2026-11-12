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
from app.services.marketing_video_agent import (
    MARKETING_TEMPLATES,
    PLATFORM_OPTIONS,
    generate_marketing_plan,
)
from app.services.minimax_video import (
    VIDEO_TEMPLATES,
    estimate_video_cost_micros,
    get_minimax_video_config,
)
from app.services.video_quality import (
    compile_i2va_prompt,
    estimate_quality_credits,
    resolve_quality_tier,
)
from app.services.professional_storyboard import provider_render_duration


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
            "images": int(asset_total or 0) + int(image_task_total or 0),
            "image_assets": int(asset_total or 0),
            "generated_images": int(image_task_total or 0),
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
) -> ImageGenerationTask:
    """创建持久商品图片任务，由调度器异步消费。"""
    if not check_feature_access(user, "ai_image"):
        raise PermissionError("图片生成功能仅限专业版套餐使用")

    aliyun_key = provider_config.get(
        "aliyun",
        "api_key",
        settings.ALIYUN_DASHSCOPE_API_KEY or "",
    )
    replicate_key = provider_config.get(
        "replicate",
        "api_key",
        settings.REPLICATE_API_KEY or "",
    )
    if not aliyun_key and not replicate_key:
        raise ValueError("图片生成功能暂未配置")

    enhanced_prompt = prompt.strip()
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

    task = ImageGenerationTask(
        user_id=user.id,
        prompt=enhanced_prompt,
        num_outputs=max(1, min(int(num_outputs or 1), 4)),
        status="pending",
        attempts=0,
        image_urls="[]",
        model_used="",
        error=None,
    )
    db.add(task)
    await db.flush()
    return task


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
) -> VideoGenerationTask:
    """校验权限、积分和首帧后提交商品图生视频任务。"""
    if not check_feature_access(user, "ai_video"):
        raise PermissionError("AI 视频生成仅限专业版套餐使用")
    if not get_minimax_video_config()["api_key"]:
        raise ValueError("AI 视频服务暂未配置")
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
    model = str(quality["model"])
    resolution = str(quality["resolution"])
    credits_cost = estimate_quality_credits(quality_tier, duration)
    estimated_cost_micros = estimate_video_cost_micros(model, resolution, duration)
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
) -> tuple[MarketingVideoProject, int]:
    """生成营销方案和分镜，不提交视频供应商，也不扣视频积分。"""
    if not check_feature_access(user, "ai_video"):
        raise PermissionError("AI 营销视频仅限专业版套餐使用")
    if not get_minimax_video_config()["api_key"]:
        raise ValueError("AI 视频服务暂未配置")
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
    model = str(quality["model"])
    resolution = str(quality["resolution"])
    credits = sum(
        estimate_quality_credits(
            quality_tier,
            provider_render_duration(model, int(item["duration"])),
        )
        for item in plan["shots"]
    )
    project = MarketingVideoProject(
        user_id=user.id,
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
