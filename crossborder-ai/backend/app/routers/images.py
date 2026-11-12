"""VeyaShip - AI 图片生成路由

生产级设计：异步任务模式 + 任务落库（CAP-07）。
用户提交生成请求 → 立即返回 task_id → 调度器从数据库队列消费 →
前端轮询结果。任务不依赖当前进程存活。

接口契约：
- POST /api/v1/images/generate  → 建库记录（pending）+ 后台执行，返回 TaskResponse
- GET  /api/v1/images/status/{task_id} → 从库读任务状态（不存在返回 404 中文）
- GET  /api/v1/images/history        → 当前用户最近 N 条记录（画廊/仪表盘，顶层路径固定）
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.user import User
from app.models.image_generation_task import ImageGenerationTask
from app.models.image_asset import ImageAsset
from app.services.image_task_executor import (
    execute_image_generation_task,
    run_image_generation,
)
from app.services import provider_config
from app.services.ai.persona_kit import (
    fetch_persona,
    build_persona_kit,
    image_style_phrase,
    strip_banned_words,
)
from app.services.image_processing import (
    create_white_background_image,
    get_platform_preset,
    list_platform_presets,
    normalize_uploaded_image,
)
from app.core.access_control import check_feature_access
from pydantic import BaseModel, Field

router = APIRouter(prefix="/images", tags=["AI 图片生成"])
AI_IMAGE_CREDITS_PER_IMAGE = 3


def image_generation_credits(num_outputs: int) -> int:
    """按图片张数计算积分，避免高成本图片生成被单积分低估。"""
    return max(1, int(num_outputs)) * AI_IMAGE_CREDITS_PER_IMAGE


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=5, description="图片描述词")
    num_outputs: int = Field(default=1, ge=1, le=4)


class TaskResponse(BaseModel):
    task_id: str
    status: str  # pending / processing / completed / failed
    image_urls: list[str] = []
    model_used: str = ""
    error: Optional[str] = None


class ImageHistoryItem(BaseModel):
    """画廊/仪表盘展示用的单条图片生成记录"""
    task_id: str
    prompt: str
    image_urls: list[str]
    model_used: str
    status: str
    created_at: str


class ImageAssetItem(BaseModel):
    id: str
    name: str
    kind: str
    image_url: str
    width: int
    height: int
    file_size: int
    preset_id: Optional[str] = None
    platform: Optional[str] = None
    background_mode: Optional[str] = None
    source_asset_id: Optional[str] = None
    created_at: str


class ImageAssetListResponse(BaseModel):
    items: list[ImageAssetItem]
    total: int


class ProcessImageRequest(BaseModel):
    preset_id: str = Field(..., min_length=1)


class PlatformPresetItem(BaseModel):
    id: str
    platform: str
    label: str
    width: int
    height: int
    note: str


def _parse_urls(raw: Optional[str]) -> list[str]:
    """把 DB 里 image_urls JSON 文本解析为列表（空/损坏返回 []）。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _asset_image_url(asset_id) -> str:
    return f"{settings.API_V1_PREFIX}/images/assets/{asset_id}/file"


def _serialize_asset(asset: ImageAsset) -> ImageAssetItem:
    return ImageAssetItem(
        id=str(asset.id),
        name=asset.name,
        kind=asset.kind,
        image_url=_asset_image_url(asset.id),
        width=asset.width,
        height=asset.height,
        file_size=asset.file_size,
        preset_id=asset.preset_id,
        platform=asset.platform,
        background_mode=asset.background_mode,
        source_asset_id=str(asset.source_asset_id) if asset.source_asset_id else None,
        created_at=str(asset.created_at),
    )


def _asset_path(storage_key: str) -> Path:
    base = Path(settings.IMAGE_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status_code=404, detail="素材文件不存在")
    return target


async def _get_owned_asset(db: AsyncSession, asset_id: str, user_id) -> ImageAsset:
    try:
        parsed_id = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="素材不存在")
    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == parsed_id,
                ImageAsset.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return asset


@router.get("/presets")
async def get_platform_presets(
    current_user: User = Depends(get_current_user),
):
    """返回跨境电商常用图片尺寸。"""
    return {"items": list_platform_presets()}


@router.post("/assets/upload", response_model=ImageAssetItem, status_code=201)
async def upload_image_asset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传商品原图并规范化为无元数据 WebP。"""
    raw = await file.read(settings.MAX_IMAGE_UPLOAD_BYTES + 1)
    try:
        normalized, width, height = await run_in_threadpool(
            normalize_uploaded_image,
            raw,
            settings.MAX_IMAGE_UPLOAD_BYTES,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    asset_id = uuid.uuid4()
    storage_key = f"{current_user.id}/{asset_id}.webp"
    target = _asset_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(normalized)

    asset = ImageAsset(
        id=asset_id,
        user_id=current_user.id,
        name=(Path(file.filename or "商品图片").stem or "商品图片")[:255],
        kind="upload",
        storage_key=storage_key,
        content_type="image/webp",
        width=width,
        height=height,
        file_size=len(normalized),
        created_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    await db.flush()
    return _serialize_asset(asset)


@router.get("/assets", response_model=ImageAssetListResponse)
async def list_image_assets(
    kind: Optional[str] = Query(None, pattern="^(upload|processed)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的上传素材和处理结果。"""
    query = select(ImageAsset).where(ImageAsset.user_id == current_user.id)
    if kind:
        query = query.where(ImageAsset.kind == kind)
    result = await db.execute(
        query.order_by(desc(ImageAsset.created_at), desc(ImageAsset.id))
    )
    assets = result.scalars().all()
    return ImageAssetListResponse(
        items=[_serialize_asset(asset) for asset in assets],
        total=len(assets),
    )


@router.get("/assets/{asset_id}/file")
async def get_image_asset_file(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
):
    """通过不可预测 UUID 地址提供图片文件，供 img 标签直接加载。"""
    try:
        parsed_id = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="素材文件不存在")
    asset = (
        await db.execute(select(ImageAsset).where(ImageAsset.id == parsed_id))
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材文件不存在")
    path = _asset_path(asset.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件不存在")
    return FileResponse(
        path,
        media_type=asset.content_type,
        filename=f"{asset.name}.{path.suffix.lstrip('.')}",
    )


@router.post("/assets/{asset_id}/process", response_model=ImageAssetItem, status_code=201)
async def process_image_asset(
    asset_id: str,
    payload: ProcessImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按平台预设生成白底适配图。"""
    source_asset = await _get_owned_asset(db, asset_id, current_user.id)
    try:
        preset = get_platform_preset(payload.preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    source_path = _asset_path(source_asset.storage_key)
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="源图片文件不存在")
    try:
        output = await run_in_threadpool(
            create_white_background_image,
            source_path.read_bytes(),
            preset["width"],
            preset["height"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    processed_id = uuid.uuid4()
    storage_key = f"{current_user.id}/{processed_id}.png"
    target = _asset_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(output)

    asset = ImageAsset(
        id=processed_id,
        user_id=current_user.id,
        name=f"{source_asset.name}-{preset['platform']}",
        kind="processed",
        storage_key=storage_key,
        content_type="image/png",
        width=preset["width"],
        height=preset["height"],
        file_size=len(output),
        preset_id=preset["id"],
        platform=preset["platform"],
        background_mode="white",
        source_asset_id=source_asset.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    await db.flush()
    return _serialize_asset(asset)


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_image_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除当前用户素材及本地文件。"""
    asset = await _get_owned_asset(db, asset_id, current_user.id)
    path = _asset_path(asset.storage_key)
    await db.delete(asset)
    await db.flush()
    if path.is_file():
        path.unlink()
    return None


async def _run_generation_impl(db: AsyncSession, task_id: str, prompt: str, num_outputs: int) -> None:
    """Backward-compatible wrapper around the durable executor."""
    await run_image_generation(db, task_id, prompt, num_outputs)


async def _run_generation(task_id: str, prompt: str, num_outputs: int, db: Optional[AsyncSession] = None) -> None:
    """执行图片生成并写库。

    传入 db 时（测试/同会话调用）用该会话；否则自建会话（生产后台任务跨请求生命周期）。
    """
    if db is not None:
        await _run_generation_impl(db, task_id, prompt, num_outputs)
        return
    async with async_session_factory() as session:
        await _run_generation_impl(session, task_id, prompt, num_outputs)


async def _execute_image_task(task_id: str, prompt: str, num_outputs: int) -> None:
    """Compatibility entrypoint for code that still calls the old helper."""
    from uuid import UUID
    try:
        tid = UUID(task_id)
    except ValueError:
        return
    await execute_image_generation_task(tid)


async def schedule_image_task(db: AsyncSession, user_id, prompt: str, num_outputs: int = 1) -> str:
    """建 pending 记录并后台调度生成；返回 task_id（供 POST /generate 与 content 主图复用）。"""
    credits_cost = image_generation_credits(num_outputs)
    task = ImageGenerationTask(
        user_id=user_id,
        prompt=prompt,
        num_outputs=num_outputs,
        status="pending",
        attempts=0,
        credits_cost=credits_cost,
        credits_charged=0,
        image_urls="[]",
        model_used="",
        error=None,
    )
    db.add(task)
    await db.flush()
    return str(task.id)


@router.post("/generate", response_model=TaskResponse)
async def generate_image(
    payload: GenerateImageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """提交图片生成任务（异步落库，立即返回 task_id）

    前端通过 GET /api/v1/images/status/{task_id} 轮询结果。
    图片路径不做文案合规拦截；品牌禁词仅做描述级简单移除，附品牌视觉风格（CAP-04）。
    """
    if not check_feature_access(current_user, "ai_image"):
        raise HTTPException(status_code=403, detail="图片生成功能仅限专业版套餐使用，请升级套餐")

    credits_cost = image_generation_credits(payload.num_outputs)
    if current_user.credits < credits_cost:
        raise HTTPException(
            status_code=402,
            detail=f"积分不足，本次图片生成需要 {credits_cost} 积分",
        )

    aliyun_key = provider_config.get("aliyun", "api_key", settings.ALIYUN_DASHSCOPE_API_KEY or "")
    replicate_key = provider_config.get("replicate", "api_key", settings.REPLICATE_API_KEY or "")
    if not aliyun_key and not replicate_key:
        raise HTTPException(status_code=400, detail="图片生成功能暂未配置")

    # 拼接品牌调性：image_style 优先，否则 tone + style；补 brand identity；去品牌禁词
    persona = await fetch_persona(db, current_user.id)
    enhanced_prompt = payload.prompt
    if persona:
        kit = build_persona_kit(persona)
        enhanced_prompt = strip_banned_words(enhanced_prompt, kit.get("banned_words") or [])
        style_phrase = image_style_phrase(kit)
        if style_phrase:
            enhanced_prompt = f"{enhanced_prompt}, {style_phrase}"
        if kit.get("brand_name"):
            enhanced_prompt = f"{enhanced_prompt}, {kit['brand_name']} brand identity"

    task_id = await schedule_image_task(db, current_user.id, enhanced_prompt, payload.num_outputs)
    return TaskResponse(task_id=task_id, status="pending")


@router.get("/status/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前用户图片生成任务状态（从库读，不存在/非本人 → 404 中文）"""
    from uuid import UUID
    try:
        tid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 只允许本人读自己的任务：他人/匿名一律 404，不暴露任务是否存在（防跨用户读图）
    result = await db.execute(
        select(ImageGenerationTask).where(
            ImageGenerationTask.id == tid,
            ImageGenerationTask.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskResponse(
        task_id=str(task.id),
        status=task.status,
        image_urls=_parse_urls(task.image_urls),
        model_used=task.model_used or "",
        error=task.error,
    )


@router.get("/history", response_model=list[ImageHistoryItem])
async def list_history(
    limit: int = Query(20, ge=1, le=100, description="返回条数，默认 20"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户最近 N 条图片生成记录（时间倒序），供画廊/仪表盘展示"""
    result = await db.execute(
        select(ImageGenerationTask)
        .where(ImageGenerationTask.user_id == current_user.id)
        .order_by(desc(ImageGenerationTask.created_at), desc(ImageGenerationTask.id))
        .limit(limit)
    )
    tasks = result.scalars().all()
    return [
        ImageHistoryItem(
            task_id=str(t.id),
            prompt=t.prompt,
            image_urls=_parse_urls(t.image_urls),
            model_used=t.model_used or "",
            status=t.status,
            created_at=str(t.created_at),
        )
        for t in tasks
    ]


@router.delete("/history/{task_id}", status_code=204)
async def delete_history_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除已完成或失败的 AI 图片生成记录。"""
    try:
        parsed_id = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="图片任务不存在")
    task = (
        await db.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.id == parsed_id,
                ImageGenerationTask.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="图片任务不存在")
    if task.status in {"pending", "processing"}:
        raise HTTPException(status_code=409, detail="图片任务仍在运行，暂时不能删除")
    await db.delete(task)
    await db.flush()
    return None
