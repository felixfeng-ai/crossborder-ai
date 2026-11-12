"""MiniMax AI 商品视频路由。"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.access_control import check_feature_access
from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.image_asset import ImageAsset
from app.models.marketing_video import MarketingVideoShot
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services.minimax_video import (
    VIDEO_TEMPLATES,
)
from app.services.video_quality import (
    compile_i2va_prompt,
    estimate_quality_credits,
    list_quality_tiers,
    list_style_presets,
    resolve_quality_tier,
)
from app.services.video_thumbnail import ensure_video_thumbnail
from app.services.video_task_executor import cancel_video_task, submit_video_task
from app.services.video_provider import (
    get_video_capabilities_summary,
    get_video_provider,
)


router = APIRouter(prefix="/videos", tags=["AI 商品视频"])


class GenerateVideoRequest(BaseModel):
    source_asset_id: str
    prompt: str = Field(default="", max_length=3000)
    template_id: str = "clean_product"
    quality_tier: str = "draft"
    style_preset: str = "commerce_showcase"
    # 保留旧字段供旧客户端提交；实际模型和分辨率由质量档位决定。
    model: str = "MiniMax-H3-Lite"
    resolution: str = "480P"
    duration: int = Field(default=4, ge=4, le=15)
    ratio: str = "9:16"


class VideoTaskResponse(BaseModel):
    id: str
    status: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    model: str
    resolution: str
    provider: str
    quality_tier: str
    style_preset: str
    credits_per_second: int
    duration: int
    ratio: str
    prompt: str
    error: Optional[str] = None
    credits_cost: int
    created_at: str
    finished_at: Optional[str] = None


def _video_file_url(task_id) -> str:
    return f"{settings.API_V1_PREFIX}/videos/tasks/{task_id}/file"


def _video_thumbnail_url(task_id) -> str:
    return f"{settings.API_V1_PREFIX}/videos/tasks/{task_id}/thumbnail"


def _serialize_task(task: VideoGenerationTask) -> VideoTaskResponse:
    return VideoTaskResponse(
        id=str(task.id),
        status=task.status,
        video_url=_video_file_url(task.id) if task.status == "succeeded" else None,
        thumbnail_url=(
            _video_thumbnail_url(task.id)
            if task.status == "succeeded"
            else None
        ),
        model=task.model,
        resolution=task.resolution,
        provider=task.provider,
        quality_tier=task.quality_tier,
        style_preset=task.style_preset,
        credits_per_second=task.credits_per_second,
        duration=task.duration,
        ratio=task.ratio,
        prompt=task.prompt,
        error=task.error,
        credits_cost=task.credits_cost,
        created_at=str(task.created_at),
        finished_at=str(task.finished_at) if task.finished_at else None,
    )


def _task_path(storage_key: str) -> Path:
    base = Path(settings.VIDEO_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return target


async def _get_owned_task(
    db: AsyncSession,
    task_id: str,
    user_id,
) -> VideoGenerationTask:
    try:
        parsed_id = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="视频任务不存在")

    task = (
        await db.execute(
            select(VideoGenerationTask).where(
                VideoGenerationTask.id == parsed_id,
                VideoGenerationTask.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="视频任务不存在")
    return task


async def _get_owned_source_asset(
    db: AsyncSession,
    source_asset_id: str,
    user_id,
) -> ImageAsset:
    try:
        parsed_id = uuid.UUID(source_asset_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="商品首帧不存在")
    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == parsed_id,
                ImageAsset.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="商品首帧不存在")
    return asset


@router.get("/capabilities")
async def video_capabilities():
    """返回可用模型、分辨率和积分估算，不暴露供应商密钥。"""
    summary = get_video_capabilities_summary()
    provider_names = {
        str(provider["provider"])
        for provider in summary["providers"]
    }
    return {
        **summary,
        "quality_tiers": list_quality_tiers(provider_names),
        "style_presets": list_style_presets(),
    }


@router.post("/generate", response_model=VideoTaskResponse, status_code=202)
async def generate_video(
    payload: GenerateVideoRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交图生视频任务；供应商受理后才扣减积分。"""
    if not check_feature_access(current_user, "ai_video"):
        raise HTTPException(status_code=403, detail="AI 视频生成仅限专业版套餐使用")
    if payload.ratio != "9:16":
        raise HTTPException(status_code=400, detail="当前仅支持 9:16 商品短视频")

    template = next(
        (item for item in VIDEO_TEMPLATES if item["id"] == payload.template_id),
        None,
    )
    if template is None:
        raise HTTPException(status_code=400, detail="视频模板不存在")

    try:
        quality_tier = resolve_quality_tier(payload.quality_tier)
        provider_name = str(quality_tier["provider"])
        provider = get_video_provider(provider_name)
        if not provider.is_configured():
            raise ValueError("所选 AI 视频服务暂未配置")
        model = str(quality_tier["model"])
        resolution = str(quality_tier["resolution"])
        credits_cost = estimate_quality_credits(
            payload.quality_tier,
            payload.duration,
        )
        estimated_cost_micros = provider.estimate_cost_micros(
            model,
            resolution,
            payload.duration,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    asset = await _get_owned_source_asset(
        db,
        payload.source_asset_id,
        current_user.id,
    )
    key = (idempotency_key or "").strip()[:100] or None
    # 行锁把同一用户的提交串行化，避免并发请求同时通过余额检查。
    locked_user = (
        await db.execute(
            select(User)
            .where(User.id == current_user.id)
            .with_for_update()
        )
    ).scalar_one()

    # 幂等重试必须在余额检查之前命中，否则首次提交扣分后重试会被误判为余额不足。
    if key:
        existing = (
            await db.execute(
                select(VideoGenerationTask).where(
                    VideoGenerationTask.user_id == current_user.id,
                    VideoGenerationTask.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _serialize_task(existing)

    if locked_user.credits < credits_cost:
        raise HTTPException(
            status_code=402,
            detail=f"积分不足，本次视频生成需要 {credits_cost} 积分",
        )

    final_prompt = compile_i2va_prompt(
        product_name=asset.name,
        direction=payload.prompt,
        duration=payload.duration,
        style_id=payload.style_preset,
        template_direction=template["prompt_suffix"],
    )

    task = VideoGenerationTask(
        user_id=current_user.id,
        source_asset_id=uuid.UUID(payload.source_asset_id),
        template_id=payload.template_id,
        provider=str(quality_tier["provider"]),
        model=model,
        resolution=resolution,
        quality_tier=payload.quality_tier,
        style_preset=payload.style_preset,
        credits_per_second=int(quality_tier["credits_per_second"]),
        duration=payload.duration,
        ratio=payload.ratio,
        prompt=final_prompt,
        status="queued",
        credits_cost=credits_cost,
        estimated_cost_micros=estimated_cost_micros,
        idempotency_key=key,
    )
    db.add(task)
    await db.flush()

    try:
        await submit_video_task(db, task)
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc) or "视频任务提交失败"
        task.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=502, detail=task.error)

    try:
        await locked_user.deduct_credits(
            db,
            credits_cost,
            feature="ai_video",
            reference_type="video_task",
            reference_id=str(task.id),
            description="商品图生视频",
        )
        task.credits_charged = credits_cost
    except Exception:
        # 供应商已经受理，任务仍可继续；本地积分异常交给调度和人工处理。
        task.error = "视频已提交，但积分扣减失败，请联系管理员"
    await db.flush()
    return _serialize_task(task)


@router.get("/tasks/{task_id}", response_model=VideoTaskResponse)
async def get_video_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(db, task_id, current_user.id)
    return _serialize_task(task)


@router.get("/history", response_model=list[VideoTaskResponse])
async def list_video_history(
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    marketing_task_ids = select(MarketingVideoShot.video_task_id).where(
        MarketingVideoShot.video_task_id.is_not(None)
    )
    tasks = (
        await db.execute(
            select(VideoGenerationTask)
            .where(
                VideoGenerationTask.user_id == current_user.id,
                VideoGenerationTask.id.not_in(marketing_task_ids),
            )
            .order_by(
                desc(VideoGenerationTask.created_at),
                desc(VideoGenerationTask.id),
            )
            .limit(limit)
        )
    ).scalars().all()
    return [_serialize_task(task) for task in tasks]


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_video_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除终态单镜头视频；营销项目镜头必须随项目一起删除。"""
    task = await _get_owned_task(db, task_id, current_user.id)
    if task.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="视频任务仍在运行，暂时不能删除")
    used_by_marketing = (
        await db.execute(
            select(MarketingVideoShot.id).where(
                MarketingVideoShot.video_task_id == task.id
            )
        )
    ).scalar_one_or_none()
    if used_by_marketing is not None:
        raise HTTPException(
            status_code=409,
            detail="该视频属于营销成片项目，请从专业分镜或营销成片中删除",
        )
    path = _task_path(task.storage_key) if task.storage_key else None
    cover_path = path.with_suffix(".cover.jpg") if path is not None else None
    await db.delete(task)
    await db.flush()
    if path is not None and path.is_file():
        path.unlink()
    if cover_path is not None:
        cover_path.unlink(missing_ok=True)
    return None


@router.post("/tasks/{task_id}/cancel", response_model=VideoTaskResponse)
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(db, task_id, current_user.id)
    if task.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="当前任务无法取消")
    if not await cancel_video_task(db, task):
        raise HTTPException(status_code=409, detail="供应商任务已结束或取消失败")
    return _serialize_task(task)


@router.get("/tasks/{task_id}/file")
async def get_video_file(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """鉴权后提供 MP4 文件，避免素材目录被匿名直链访问。"""
    task = await _get_owned_task(db, task_id, current_user.id)
    if task.status != "succeeded" or not task.storage_key:
        raise HTTPException(status_code=404, detail="视频文件不存在")
    path = _task_path(task.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return FileResponse(
        path,
        media_type=task.mime or "video/mp4",
        filename=f"veyaship-{task.id}.mp4",
    )


@router.get("/tasks/{task_id}/thumbnail")
async def get_video_thumbnail(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """通过不可猜测任务 UUID 提供懒生成封面。"""
    try:
        parsed_id = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="视频封面不存在")
    task = (
        await db.execute(
            select(VideoGenerationTask).where(
                VideoGenerationTask.id == parsed_id,
                VideoGenerationTask.status == "succeeded",
            )
        )
    ).scalar_one_or_none()
    if task is None or not task.storage_key:
        raise HTTPException(status_code=404, detail="视频封面不存在")
    video_path = _task_path(task.storage_key)
    try:
        cover_path = await run_in_threadpool(ensure_video_thumbnail, video_path)
    except (FileNotFoundError, RuntimeError):
        raise HTTPException(status_code=404, detail="视频封面不存在")
    return FileResponse(
        cover_path,
        media_type="image/jpeg",
        filename=f"veyaship-{task.id}.cover.jpg",
    )
