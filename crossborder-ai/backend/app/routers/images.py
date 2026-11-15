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
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.user import User
from app.models.image_generation_task import ImageGenerationTask
from app.models.image_asset import ImageAsset
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_image_suite import (
    MarketingImageSuite,
    MarketingImageSuiteItem,
)
from app.services.image_task_executor import (
    execute_image_generation_task,
    run_image_generation,
)
from app.services.generated_image_assets import materialize_image_task_assets
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
from app.services.image_quality import (
    estimate_image_cost_micros,
    image_generation_credits as calculate_image_credits,
    public_image_capabilities,
    resolve_image_resolution,
)
from app.services.image_editing_service import create_image_edit_task
from app.services.image_provider import list_image_provider_capabilities
from app.services.marketing_image_suite_service import (
    create_marketing_image_suite,
    normalize_suite_platforms,
    serialize_marketing_image_suite,
)
from app.core.access_control import check_feature_access
from pydantic import BaseModel, Field

router = APIRouter(prefix="/images", tags=["AI 图片生成"])


class GenerateImageRequest(BaseModel):
    """兼容旧接口的图片生成请求；未传 mode 时按 legacy 处理。"""

    prompt: str = Field(..., min_length=1, description="图片描述词")
    mode: Optional[
        Literal["product_scene", "free_creation", "platform_white"]
    ] = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    platform_preset_id: Optional[str] = None
    quality_tier: Optional[Literal["fast", "standard", "hd"]] = None
    aspect_ratio: str = Field(default="1:1", max_length=12)
    resolution: Optional[str] = Field(default=None, max_length=24)
    negative_prompt: str = Field(default="", max_length=2000)
    style_preset: Optional[str] = Field(default=None, max_length=80)
    use_brand_persona: Optional[bool] = None
    provider: Literal["auto", "seedream", "aliyun", "replicate"] = "auto"
    num_outputs: int = Field(default=1, ge=1, le=4)
    campaign_id: Optional[str] = Field(None, description="营销活动 ID")
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="客户端请求幂等键",
    )


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
    mode: str = "legacy"
    quality_tier: Optional[str] = None
    provider: str = "auto"


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
    generation_task_id: Optional[str] = None
    variant_index: Optional[int] = None
    created_at: str


class ImageAssetListResponse(BaseModel):
    items: list[ImageAssetItem]
    total: int


class ProcessImageRequest(BaseModel):
    preset_id: str = Field(..., min_length=1)


class RenameImageAssetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class PlatformPresetItem(BaseModel):
    id: str
    platform: str
    label: str
    width: int
    height: int
    note: str


class MarketingImageSuiteRequest(BaseModel):
    """营销套图请求；平台至少两个，参考图 1-4 张。"""

    campaign_id: str
    title: str = Field(..., min_length=1, max_length=255)
    direction: Literal[
        "conversion",
        "lifestyle",
        "campaign",
        "premium",
    ] = "conversion"
    theme: str = Field(default="", max_length=80)
    platforms: list[str] = Field(..., min_length=2, max_length=5)
    reference_asset_ids: list[str] = Field(..., min_length=1, max_length=4)
    quality_tier: Literal["fast", "standard", "hd"] = "fast"
    note: str = Field(default="", max_length=800)
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=100,
    )


class ImageEditRequest(BaseModel):
    """图片编辑请求；蒙版仅局部编辑需要。"""

    source_asset_id: str
    operation: Literal[
        "inpaint",
        "outpaint",
        "remove_object",
        "upscale",
    ]
    mask_asset_id: Optional[str] = None
    prompt: str = Field(default="", max_length=2000)
    aspect_ratio: str = Field(default="", max_length=12)
    scale: int = Field(default=2, ge=2, le=4)
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
    )


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
        generation_task_id=(
            str(asset.generation_task_id) if asset.generation_task_id else None
        ),
        variant_index=asset.variant_index,
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


@router.get("/capabilities")
async def get_image_capabilities(
    current_user: User = Depends(get_current_user),
):
    """返回图片工作台支持的模式、质量档和积分矩阵。"""
    payload = public_image_capabilities()
    payload["providers"] = list_image_provider_capabilities()
    return payload


@router.post("/marketing-suites", status_code=201)
async def create_image_marketing_suite(
    payload: MarketingImageSuiteRequest,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """创建营销多平台套图；校验、建套图和多任务在同一事务内完成。"""
    try:
        # 路由层先校验平台，避免无效请求进入后续素材和活动查询。
        normalize_suite_platforms(payload.platforms)
        suite = await create_marketing_image_suite(
            db,
            current_user,
            campaign_id=payload.campaign_id,
            title=payload.title,
            direction=payload.direction,
            theme=payload.theme,
            platform_ids=payload.platforms,
            reference_asset_ids=payload.reference_asset_ids,
            quality_tier=payload.quality_tier,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
        )
        data = await serialize_marketing_image_suite(db, suite)
        await db.commit()
        return data
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        await db.rollback()
        status_code = 402 if "积分不足" in str(exc) else 404 if (
            "不存在" in str(exc)
        ) else 400
        raise HTTPException(status_code=status_code, detail=str(exc))


@router.post("/edit", status_code=201)
async def create_image_edit(
    payload: ImageEditRequest,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """创建局部重绘、扩图、消除或本地放大任务。"""
    try:
        task = await create_image_edit_task(
            db,
            current_user,
            source_asset_id=payload.source_asset_id,
            operation=payload.operation,
            mask_asset_id=payload.mask_asset_id,
            prompt=payload.prompt,
            aspect_ratio=payload.aspect_ratio,
            scale=payload.scale,
            idempotency_key=payload.idempotency_key,
        )
        await db.commit()
        return TaskResponse(
            task_id=str(task.id),
            status=task.status,
            image_urls=_parse_urls(task.image_urls),
            model_used=task.model_used or "",
            error=task.error,
        )
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        await db.rollback()
        message = str(exc)
        status_code = 402 if "积分不足" in message else 404 if (
            "素材不存在" in message
        ) else 400
        raise HTTPException(status_code=status_code, detail=message)


@router.get("/marketing-suites")
async def list_image_marketing_suites(
    campaign_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按活动列出当前用户的套图摘要。"""
    query = select(MarketingImageSuite).where(
        MarketingImageSuite.user_id == current_user.id
    )
    if campaign_id:
        try:
            campaign_uuid = uuid.UUID(campaign_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="营销活动不存在")
        query = query.where(MarketingImageSuite.campaign_id == campaign_uuid)
    suites = (
        await db.execute(
            query.order_by(desc(MarketingImageSuite.created_at)).limit(50)
        )
    ).scalars().all()
    items = [
        await serialize_marketing_image_suite(db, suite)
        for suite in suites
    ]
    return {"items": items, "total": len(items)}


@router.get("/marketing-suites/{suite_id}")
async def get_image_marketing_suite(
    suite_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed_id = uuid.UUID(suite_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="营销套图不存在")
    suite = (
        await db.execute(
            select(MarketingImageSuite).where(
                MarketingImageSuite.id == parsed_id,
                MarketingImageSuite.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if suite is None:
        raise HTTPException(status_code=404, detail="营销套图不存在")
    return await serialize_marketing_image_suite(db, suite)


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
    kind: Optional[str] = Query(None, pattern="^(upload|processed|generated)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的上传、白底处理和 AI 生成素材。"""
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


@router.patch("/assets/{asset_id}", response_model=ImageAssetItem)
async def rename_image_asset(
    asset_id: str,
    payload: RenameImageAssetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名当前用户的素材变体。"""
    asset = await _get_owned_asset(db, asset_id, current_user.id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="素材名称不能为空")
    asset.name = name
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
    generation_task_id = asset.generation_task_id
    await db.delete(asset)
    await db.flush()
    if generation_task_id is not None:
        remaining = (
            await db.execute(
                select(ImageAsset.id).where(
                    ImageAsset.generation_task_id == generation_task_id
                )
            )
        ).scalars().all()
        if not remaining:
            task = await db.get(ImageGenerationTask, generation_task_id)
            if task is not None:
                # 最后一个变体删除后清空远端结果，避免活动素材板重新出现。
                task.image_urls = "[]"
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


async def schedule_image_task(
    db: AsyncSession,
    user_id,
    prompt: str,
    num_outputs: int = 1,
    campaign_id: Optional[uuid.UUID] = None,
    *,
    mode: str = "legacy",
    quality_tier: Optional[str] = None,
    provider: str = "auto",
    resolution: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    style_preset: Optional[str] = None,
    use_brand_persona: bool = False,
    reference_asset_ids: Optional[list[str]] = None,
    idempotency_key: Optional[str] = None,
) -> str:
    """建 pending 记录并后台调度生成；返回 task_id（供 POST /generate 与 content 主图复用）。"""
    credits_cost = calculate_image_credits(mode, quality_tier or "fast", num_outputs)
    reference_ids = reference_asset_ids or []
    task = ImageGenerationTask(
        user_id=user_id,
        campaign_id=campaign_id,
        prompt=prompt,
        num_outputs=num_outputs,
        mode=mode,
        quality_tier=quality_tier,
        provider=provider,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        negative_prompt=negative_prompt,
        style_preset=style_preset,
        use_brand_persona=use_brand_persona,
        reference_assets_json=json.dumps(reference_ids),
        reference_coverage="provided" if reference_ids else "none",
        generation_params_json=json.dumps(
            {
                "mode": mode,
                "quality_tier": quality_tier,
                "provider": provider,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "style_preset": style_preset,
            },
            ensure_ascii=False,
        ),
        estimated_cost_micros=estimate_image_cost_micros(
            mode,
            quality_tier or "fast",
            num_outputs,
        ),
        idempotency_key=idempotency_key,
        status="pending",
        attempts=0,
        credits_cost=credits_cost,
        credits_charged=0,
        image_urls="[]",
        model_used="",
        error=None,
    )
    db.add(task)
    try:
        await db.flush()
    except IntegrityError:
        # 并发重试同一幂等键时，回滚当前插入并返回已存在任务。
        await db.rollback()
        existing = (
            await db.execute(
                select(ImageGenerationTask).where(
                    ImageGenerationTask.user_id == user_id,
                    ImageGenerationTask.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one()
        return str(existing.id)
    return str(task.id)


def _image_mode(payload: GenerateImageRequest) -> str:
    """兼容历史客户端：未声明模式时进入 legacy 计费和品牌链路。"""
    return payload.mode or "legacy"


def _image_quality_tier(payload: GenerateImageRequest, mode: str) -> Optional[str]:
    if mode == "legacy":
        return None
    return payload.quality_tier or "standard"


_REALISM_HINTS = (
    "真人",
    "写实",
    "照片",
    "摄影",
    "人像",
    "自然皮肤",
    "皮肤质感",
)
_REALISM_NEGATIVE_PROMPT = (
    "塑料皮肤，蜡像感，过度磨皮，五官失真，错误手指，肢体畸形，"
    "卡通，插画，CGI感"
)


def _enhance_realism_negative_prompt(prompt: str, negative_prompt: str) -> str:
    """识别写实意图时补充通用负面约束，避免人物呈现蜡像或过度磨皮。"""
    if not any(hint in prompt for hint in _REALISM_HINTS):
        return negative_prompt
    existing = negative_prompt.strip()
    if not existing:
        return _REALISM_NEGATIVE_PROMPT
    return f"{existing}，{_REALISM_NEGATIVE_PROMPT}"


async def _resolve_reference_assets(
    db: AsyncSession,
    payload: GenerateImageRequest,
    user_id,
) -> list[ImageAsset]:
    """逐张校验参考图归属；跨用户素材统一返回 404，避免泄露存在性。"""
    if not payload.reference_asset_ids:
        if _image_mode(payload) == "product_scene":
            raise HTTPException(status_code=400, detail="商品场景至少需要 1 张参考图")
        return []
    ids = list(dict.fromkeys(payload.reference_asset_ids))
    if len(ids) > 4:
        raise HTTPException(status_code=400, detail="商品场景最多支持 4 张参考图")

    parsed_ids = []
    for raw_id in ids:
        try:
            parsed_ids.append(uuid.UUID(raw_id))
        except ValueError:
            raise HTTPException(status_code=404, detail="参考素材不存在")
    assets = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id.in_(parsed_ids),
                ImageAsset.user_id == user_id,
            )
        )
    ).scalars().all()
    if len(assets) != len(parsed_ids):
        raise HTTPException(status_code=404, detail="参考素材不存在")
    return assets


def _configured_image_providers() -> dict[str, bool]:
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
    reference_model = provider_config.get(
        "replicate",
        "reference_model",
        settings.REPLICATE_IMAGE_REFERENCE_MODEL or "",
    )
    from app.services.ai.seedream_image import get_seedream_image_config

    seedream_key = get_seedream_image_config()["api_key"]
    return {
        "aliyun": bool(aliyun_key),
        "replicate": bool(replicate_key),
        "replicate_reference": bool(replicate_key and reference_model),
        "seedream": bool(seedream_key),
    }


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

    mode = _image_mode(payload)
    quality_tier = _image_quality_tier(payload, mode)

    # 同一用户重复提交相同幂等键时直接复用任务，不重复建任务或扣积分。
    if payload.idempotency_key:
        existing = (
            await db.execute(
                select(ImageGenerationTask).where(
                    ImageGenerationTask.user_id == current_user.id,
                    ImageGenerationTask.idempotency_key == payload.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return TaskResponse(
                task_id=str(existing.id),
                status=existing.status,
                image_urls=_parse_urls(existing.image_urls),
                model_used=existing.model_used or "",
                error=existing.error,
            )

    campaign_uuid = None
    if payload.campaign_id:
        try:
            campaign_uuid = uuid.UUID(payload.campaign_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="营销活动不存在")
        campaign = (
            await db.execute(
                select(MarketingCampaign).where(
                    MarketingCampaign.id == campaign_uuid,
                    MarketingCampaign.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=404, detail="营销活动不存在")

    reference_assets = await _resolve_reference_assets(
        db,
        payload,
        current_user.id,
    )
    provider_status = _configured_image_providers()
    if mode == "product_scene":
        if payload.provider == "aliyun":
            raise HTTPException(
                status_code=400,
                detail="商品场景参考图请选择 Seedream 或 Replicate",
            )
        if payload.provider == "seedream" and not provider_status["seedream"]:
            raise HTTPException(
                status_code=400,
                detail="Seedream 图片服务暂未配置，请管理员检查方舟 API Key",
            )
        if (
            payload.provider == "replicate"
            and not provider_status["replicate_reference"]
        ):
            raise HTTPException(
                status_code=400,
                detail="Replicate 参考图服务暂未配置，请管理员检查 API Key 和参考图模型",
            )
        if (
            payload.provider == "auto"
            and not provider_status["seedream"]
            and not provider_status["replicate_reference"]
        ):
            raise HTTPException(
                status_code=400,
                detail="商品场景参考图服务暂未配置，请管理员配置 Seedream 或 Replicate",
            )
    elif payload.provider == "aliyun" and not provider_status["aliyun"]:
        raise HTTPException(status_code=400, detail="阿里云图片生成服务暂未配置")
    elif payload.provider == "replicate" and not provider_status["replicate"]:
        raise HTTPException(status_code=400, detail="Replicate 图片生成服务暂未配置")
    elif payload.provider == "seedream" and not provider_status["seedream"]:
        raise HTTPException(
            status_code=400,
            detail="Seedream 图片生成服务暂未配置，请管理员检查方舟 API Key",
        )
    elif (
        mode != "platform_white"
        and not provider_status["aliyun"]
        and not provider_status["replicate"]
        and not provider_status["seedream"]
    ):
        raise HTTPException(status_code=400, detail="图片生成功能暂未配置")

    try:
        credits_cost = calculate_image_credits(
            mode,
            quality_tier or "fast",
            payload.num_outputs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if current_user.credits < credits_cost:
        raise HTTPException(
            status_code=402,
            detail=f"积分不足，本次图片生成需要 {credits_cost} 积分",
        )

    # 拼接品牌调性：image_style 优先，否则 tone + style；补 brand identity；去品牌禁词
    enhanced_prompt = payload.prompt
    negative_prompt = _enhance_realism_negative_prompt(
        payload.prompt,
        payload.negative_prompt,
    )
    use_brand_persona = (
        payload.use_brand_persona
        if payload.use_brand_persona is not None
        else mode != "free_creation"
    )
    if use_brand_persona:
        persona = await fetch_persona(db, current_user.id)
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

    resolution = payload.resolution or resolve_image_resolution(
        quality_tier or "fast",
        payload.aspect_ratio,
    )

    task_id = await schedule_image_task(
        db,
        current_user.id,
        enhanced_prompt,
        payload.num_outputs,
        campaign_uuid,
        mode=mode,
        quality_tier=quality_tier,
        provider=payload.provider,
        resolution=resolution,
        aspect_ratio=payload.aspect_ratio,
        negative_prompt=negative_prompt,
        style_preset=payload.style_preset,
        use_brand_persona=use_brand_persona,
        reference_asset_ids=[
            str(asset.id)
            for asset in reference_assets
        ],
        idempotency_key=payload.idempotency_key,
    )
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
            mode=t.mode,
            quality_tier=t.quality_tier,
            provider=t.provider,
        )
        for t in tasks
    ]


@router.post(
    "/history/{task_id}/materialize",
    response_model=ImageAssetListResponse,
)
async def materialize_history_images(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把已完成的历史生成图补入库，供视频首帧和素材中心复用。"""
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
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="图片任务尚未完成")
    urls = _parse_urls(task.image_urls)
    if not urls:
        raise HTTPException(status_code=409, detail="图片任务暂无可入库结果")

    assets = await materialize_image_task_assets(
        db,
        user_id=current_user.id,
        task_id=task.id,
        prompt=task.prompt,
        image_urls=urls,
    )
    return ImageAssetListResponse(
        items=[_serialize_asset(asset) for asset in assets],
        total=len(assets),
    )


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
    generated_assets = (
        await db.execute(
            select(ImageAsset).where(ImageAsset.generation_task_id == task.id)
        )
    ).scalars().all()
    generated_paths = [_asset_path(asset.storage_key) for asset in generated_assets]
    await db.delete(task)
    await db.flush()
    for path in generated_paths:
        if path.is_file():
            path.unlink(missing_ok=True)
    return None
