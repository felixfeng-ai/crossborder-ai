"""AI 营销视频 Agent 路由。"""

import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import check_feature_access
from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.image_asset import ImageAsset
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.user import InsufficientCreditsError, User
from app.models.video_generation_task import VideoGenerationTask
from app.services.ai.persona_kit import build_persona_kit, fetch_persona, format_persona_block
from app.services.marketing_video_agent import (
    MARKETING_TEMPLATES,
    PLATFORM_OPTIONS,
    estimate_marketing_plan_credits,
    generate_marketing_plan,
)
from app.services.marketing_video_executor import (
    cancel_marketing_project,
    start_marketing_project,
)
from app.services.marketing_subtitles import build_marketing_srt
from app.services.minimax_tts import (
    MiniMaxTTSNotConfigured,
    MiniMaxTTSError,
    get_minimax_tts_capabilities,
    synthesize_minimax_tts,
)
from app.services.minimax_video import (
    get_minimax_video_capabilities,
    get_minimax_video_config,
)
from app.services.professional_storyboard import (
    MAX_SCRIPT_CHARS,
    build_reference_asset_prompt,
    build_shot_prompt,
    estimate_storyboard_credits,
    parse_professional_storyboard,
    provider_render_duration,
)


router = APIRouter(prefix="/marketing-videos", tags=["AI 营销视频"])

SUPPORTED_DURATIONS = {15, 20, 30}
REFERENCE_ROLES = {
    "front",
    "back",
    "detail",
    "package",
    "structure",
    "logo",
    "scale",
    "lifestyle",
}


class ProductReferenceAssetInput(BaseModel):
    """商品参考图及用途，供供应商多图参考提示词使用。"""

    asset_id: str
    role: Literal[
        "front",
        "back",
        "detail",
        "package",
        "structure",
        "logo",
        "scale",
        "lifestyle",
    ] = "detail"


class ProductReferenceAssetResponse(BaseModel):
    asset_id: str
    role: str
    is_primary: bool


class CreateMarketingProjectRequest(BaseModel):
    source_asset_id: str
    reference_assets: list[ProductReferenceAssetInput] = Field(default_factory=list)
    continuity_mode: Literal["natural"] = "natural"
    idea: str = Field(..., min_length=3, max_length=3000)
    product_name: str = Field(..., min_length=1, max_length=255)
    platform: str = "tiktok"
    market: str = Field("US", min_length=2, max_length=50)
    language: str = Field("en", min_length=2, max_length=30)
    duration: int = 15
    template_id: str = "presenter_demo"
    model: str = "MiniMax-H3-Lite"
    resolution: str = "480P"


class StoryboardPreviewRequest(BaseModel):
    script: str = Field(..., min_length=1, max_length=MAX_SCRIPT_CHARS)


class CreateStoryboardProjectRequest(StoryboardPreviewRequest):
    source_asset_id: str
    reference_assets: list[ProductReferenceAssetInput] = Field(default_factory=list)
    continuity_mode: Literal["natural"] = "natural"
    product_name: str = Field(..., min_length=1, max_length=255)
    platform: str = "tiktok"
    market: str = Field("US", min_length=2, max_length=50)
    language: str = Field("en", min_length=2, max_length=30)
    model: str = "MiniMax-H3-Lite"
    resolution: str = "480P"


class MarketingShotResponse(BaseModel):
    position: int
    title: str
    purpose: str
    prompt: str
    source_text: Optional[str] = None
    start_seconds: int = 0
    end_seconds: int = 0
    duration: int
    status: str
    video_url: Optional[str] = None
    error: Optional[str] = None


class MarketingProjectResponse(BaseModel):
    id: str
    title: str
    product_name: str
    idea: str
    platform: str
    market: str
    language: str
    duration: int
    template_id: str
    mode: str = "creative"
    reference_assets: list[ProductReferenceAssetResponse] = Field(default_factory=list)
    continuity_mode: str = "natural"
    script_text: Optional[str] = None
    continuity: dict = Field(default_factory=dict)
    model: str
    resolution: str
    status: str
    brief: dict
    shots: list[MarketingShotResponse]
    credits_estimated: int
    credits_charged: int
    credits_refunded: int
    video_available: bool = False
    final_video_url: Optional[str] = None
    subtitle_url: Optional[str] = None
    subtitles_burned_in: bool = False
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None


async def _asset_owned(
    db: AsyncSession,
    source_asset_id: str,
    user_id,
) -> ImageAsset:
    try:
        asset_id = uuid.UUID(source_asset_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="商品首帧不存在")
    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="商品首帧不存在")
    return asset


async def _normalize_reference_assets(
    db: AsyncSession,
    primary_asset_id: str,
    references: list[ProductReferenceAssetInput],
    user_id,
) -> list[dict]:
    """校验主图与参考图归属、数量和用途，并生成稳定的发送顺序。"""
    try:
        primary_id = uuid.UUID(primary_asset_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="商品主图不存在")

    reference_ids: list[uuid.UUID] = []
    for item in references:
        try:
            reference_ids.append(uuid.UUID(item.asset_id))
        except ValueError:
            raise HTTPException(status_code=404, detail="商品参考图不存在")
    if primary_id in reference_ids:
        raise HTTPException(status_code=400, detail="主图不能重复作为参考图")
    if len({str(asset_id) for asset_id in reference_ids}) != len(reference_ids):
        raise HTTPException(status_code=400, detail="商品参考图不能重复")
    if len(reference_ids) + 1 > 9:
        raise HTTPException(status_code=400, detail="商品主图和参考图合计最多支持 9 张")

    if reference_ids:
        assets = (
            await db.execute(
                select(ImageAsset).where(
                    ImageAsset.id.in_(reference_ids),
                    ImageAsset.user_id == user_id,
                )
            )
        ).scalars().all()
        if len(assets) != len(reference_ids):
            raise HTTPException(status_code=404, detail="商品参考图不存在")

    normalized = [
        {
            "asset_id": str(primary_id),
            "role": "front",
            "is_primary": True,
        }
    ]
    normalized.extend(
        {
            "asset_id": str(item.asset_id),
            "role": item.role,
            "is_primary": False,
        }
        for item in references
    )
    return normalized


async def _owned_project(
    db: AsyncSession,
    project_id: str,
    user_id,
) -> MarketingVideoProject:
    try:
        parsed_id = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="营销视频项目不存在")
    project = (
        await db.execute(
            select(MarketingVideoProject).where(
                MarketingVideoProject.id == parsed_id,
                MarketingVideoProject.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="营销视频项目不存在")
    return project


def _project_file_path(storage_key: str) -> Path:
    base = Path(settings.VIDEO_STORAGE_DIR).resolve()
    target = (base / storage_key).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=404, detail="营销成片不存在")
    return target


def _safe_filename_part(value: str, fallback: str) -> str:
    """清理文件名中的系统非法字符，并限制过长的商品名称。"""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", value or "")
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip("-. ")
    return cleaned[:80] or fallback


def _marketing_download_filename(
    project: MarketingVideoProject,
    extension: Literal["mp4", "srt", "mp3"],
) -> str:
    """使用商品名和平台生成用户可读的下载文件名。"""
    product = _safe_filename_part(project.product_name or project.title, "商品视频")
    platform = _safe_filename_part(project.platform, "video")
    labels = {
        "mp4": "营销成片",
        "srt": "营销成片字幕",
        "mp3": "AI配音",
    }
    return f"{product}-{platform}-{labels[extension]}.{extension}"


def _attachment_disposition(filename: str) -> str:
    """按 RFC 5987 编码中文文件名，避免响应头出现编码异常。"""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def _parse_brief(project: MarketingVideoProject) -> dict:
    try:
        value = json.loads(project.brief_json)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_reference_assets(project: MarketingVideoProject) -> list[dict]:
    """读取项目商品参考图；损坏或空值回退为空列表。"""
    try:
        value = json.loads(project.reference_assets_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


async def _serialize_project(
    db: AsyncSession,
    project: MarketingVideoProject,
) -> MarketingProjectResponse:
    shots = (
        await db.execute(
            select(MarketingVideoShot)
            .where(MarketingVideoShot.project_id == project.id)
            .order_by(MarketingVideoShot.position)
        )
    ).scalars().all()
    task_ids = [shot.video_task_id for shot in shots if shot.video_task_id]
    tasks = (
        await db.execute(
            select(VideoGenerationTask).where(VideoGenerationTask.id.in_(task_ids))
        )
    ).scalars().all() if task_ids else []
    task_by_id = {task.id: task for task in tasks}

    shot_items = []
    cursor_seconds = 0
    for shot in shots:
        task = task_by_id.get(shot.video_task_id)
        start_seconds = cursor_seconds
        end_seconds = start_seconds + shot.duration
        cursor_seconds = end_seconds
        shot_items.append(
            MarketingShotResponse(
                position=shot.position,
                title=shot.title,
                purpose=shot.purpose,
                prompt=shot.prompt,
                source_text=shot.source_text,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                duration=shot.duration,
                status=shot.status,
                video_url=(
                    f"{settings.API_V1_PREFIX}/videos/tasks/{task.id}/file"
                    if task and task.status == "succeeded"
                    else None
                ),
                error=shot.error,
            )
        )
    brief = _parse_brief(project)
    try:
        continuity = json.loads(project.continuity_json or "{}")
    except (json.JSONDecodeError, TypeError):
        continuity = {}
    video_available = bool(
        project.status == "succeeded"
        and project.final_storage_key
        and _project_file_path(project.final_storage_key).is_file()
    )
    return MarketingProjectResponse(
        id=str(project.id),
        title=project.title,
        product_name=project.product_name,
        idea=project.idea,
        platform=project.platform,
        market=project.market,
        language=project.language,
        duration=project.duration,
        template_id=project.template_id,
        mode=project.mode or "creative",
        reference_assets=_parse_reference_assets(project),
        continuity_mode=(
            "strict" if continuity.get("mode") == "strict" else "natural"
        ),
        script_text=project.script_text,
        continuity=continuity if isinstance(continuity, dict) else {},
        model=project.model,
        resolution=project.resolution,
        status=project.status,
        brief=brief,
        shots=shot_items,
        credits_estimated=project.credits_estimated,
        credits_charged=project.credits_charged,
        credits_refunded=project.credits_refunded,
        video_available=video_available,
        final_video_url=(
            f"{settings.API_V1_PREFIX}/marketing-videos/projects/{project.id}/file"
            if video_available
            else None
        ),
        subtitle_url=(
            None
            if project.mode == "script" or brief.get("no_subtitles")
            else (
                f"{settings.API_V1_PREFIX}/marketing-videos/projects/"
                f"{project.id}/subtitles"
            )
        ),
        subtitles_burned_in=bool(project.subtitles_burned_in),
        error=project.error,
        created_at=str(project.created_at),
        finished_at=str(project.finished_at) if project.finished_at else None,
    )


@router.get("/capabilities")
async def marketing_video_capabilities():
    video = get_minimax_video_capabilities()
    return {
        **video,
        "voice": get_minimax_tts_capabilities(),
        "platforms": list(PLATFORM_OPTIONS),
        "marketing_templates": list(MARKETING_TEMPLATES),
        "durations": sorted(SUPPORTED_DURATIONS),
    }


@router.post("/storyboards/preview")
async def preview_professional_storyboard(
    payload: StoryboardPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """解析专业脚本文案，不调用 LLM，也不扣积分。"""
    if not check_feature_access(current_user, "ai_video"):
        raise HTTPException(status_code=403, detail="专业分镜仅限专业版套餐使用")
    try:
        storyboard = parse_professional_storyboard(payload.script)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return storyboard.to_dict()


@router.post("/storyboards/projects", response_model=MarketingProjectResponse, status_code=201)
async def create_professional_storyboard_project(
    payload: CreateStoryboardProjectRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """原样保存用户分镜并创建可逐镜头渲染的专业项目。"""
    if not check_feature_access(current_user, "ai_video"):
        raise HTTPException(status_code=403, detail="专业分镜仅限专业版套餐使用")
    if not get_minimax_video_config()["api_key"]:
        raise HTTPException(status_code=400, detail="AI 视频服务暂未配置")
    if not any(item["id"] == payload.platform for item in PLATFORM_OPTIONS):
        raise HTTPException(status_code=400, detail="目标平台不支持")
    try:
        storyboard = parse_professional_storyboard(payload.script)
        credits = estimate_storyboard_credits(
            storyboard.shots,
            model=payload.model,
            resolution=payload.resolution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await _asset_owned(db, payload.source_asset_id, current_user.id)
    reference_assets = await _normalize_reference_assets(
        db,
        payload.source_asset_id,
        payload.reference_assets,
        current_user.id,
    )
    await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    key = (idempotency_key or "").strip()[:100] or None
    if key:
        existing = (
            await db.execute(
                select(MarketingVideoProject).where(
                    MarketingVideoProject.user_id == current_user.id,
                    MarketingVideoProject.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _serialize_project(db, existing)

    continuity = {
        "mode": payload.continuity_mode,
        "global_constraints": storyboard.global_constraints,
        "no_dialogue": storyboard.no_dialogue,
        "no_subtitles": storyboard.no_subtitles,
        "no_watermark": storyboard.no_watermark,
        "preamble": storyboard.preamble,
    }
    title = (
        f"{payload.product_name} · {storyboard.title}"
        if storyboard.title != "专业脚本分镜"
        else f"{payload.product_name} · 专业分镜"
    )
    brief = {
        **storyboard.to_dict(),
        "mode": "script",
        "title": title,
        "hook": storyboard.shots[0].title,
        "script": "",
        "cta": "",
    }
    project = MarketingVideoProject(
        user_id=current_user.id,
        source_asset_id=uuid.UUID(payload.source_asset_id),
        reference_assets_json=json.dumps(reference_assets, ensure_ascii=False),
        title=title[:255],
        product_name=payload.product_name,
        idea=f"专业脚本分镜 · {storyboard.shot_count} 个镜头",
        platform=payload.platform,
        market=payload.market,
        language=payload.language,
        duration=storyboard.total_duration,
        template_id="professional_script",
        mode="script",
        script_text=payload.script,
        continuity_json=json.dumps(continuity, ensure_ascii=False),
        model=payload.model,
        resolution=payload.resolution,
        status="brief_ready",
        brief_json=json.dumps(brief, ensure_ascii=False),
        credits_estimated=credits,
        idempotency_key=key,
    )
    db.add(project)
    await db.flush()
    for index, shot in enumerate(storyboard.shots):
        db.add(
            MarketingVideoShot(
                project_id=project.id,
                position=shot.position,
                title=shot.title,
                purpose=shot.purpose,
                prompt=build_shot_prompt(
                    shot,
                    product_name=payload.product_name,
                    global_constraints=storyboard.global_constraints,
                    no_dialogue=storyboard.no_dialogue,
                    no_subtitles=storyboard.no_subtitles,
                    no_watermark=storyboard.no_watermark,
                    previous_shot=storyboard.shots[index - 1] if index > 0 else None,
                    next_shot=(
                        storyboard.shots[index + 1]
                        if index + 1 < storyboard.shot_count
                        else None
                    ),
                    reference_assets=reference_assets,
                ),
                source_text=shot.source_text,
                duration=shot.duration,
                status="planned",
            )
        )
    await db.flush()
    return await _serialize_project(db, project)


@router.post("/projects", response_model=MarketingProjectResponse, status_code=201)
async def create_marketing_project(
    payload: CreateMarketingProjectRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成营销方案与分镜，不调用视频供应商。"""
    if not check_feature_access(current_user, "ai_video"):
        raise HTTPException(status_code=403, detail="AI 营销视频仅限专业版套餐使用")
    if not get_minimax_video_config()["api_key"]:
        raise HTTPException(status_code=400, detail="AI 视频服务暂未配置")
    if payload.duration not in SUPPORTED_DURATIONS:
        raise HTTPException(status_code=400, detail="营销视频时长仅支持 15、20、30 秒")
    if not any(item["id"] == payload.platform for item in PLATFORM_OPTIONS):
        raise HTTPException(status_code=400, detail="目标平台不支持")
    if not any(item["id"] == payload.template_id for item in MARKETING_TEMPLATES):
        raise HTTPException(status_code=400, detail="营销视频模板不存在")
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="积分不足，生成营销方案需要 1 积分")

    await _asset_owned(db, payload.source_asset_id, current_user.id)
    reference_assets = await _normalize_reference_assets(
        db,
        payload.source_asset_id,
        payload.reference_assets,
        current_user.id,
    )
    (
        await db.execute(
            select(User).where(User.id == current_user.id).with_for_update()
        )
    ).scalar_one()
    key = (idempotency_key or "").strip()[:100] or None
    if key:
        existing = (
            await db.execute(
                select(MarketingVideoProject).where(
                    MarketingVideoProject.user_id == current_user.id,
                    MarketingVideoProject.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _serialize_project(db, existing)

    persona = await fetch_persona(db, current_user.id)
    brand_context = format_persona_block(build_persona_kit(persona)) if persona else None
    plan = await generate_marketing_plan(
        idea=payload.idea,
        product_name=payload.product_name,
        platform=payload.platform,
        market=payload.market,
        language=payload.language,
        duration=payload.duration,
        template_id=payload.template_id,
        brand_context=brand_context,
    )
    reference_prompt = build_reference_asset_prompt(reference_assets)
    if reference_prompt:
        for item in plan["shots"]:
            item["prompt"] = f"{item['prompt']}\n\n{reference_prompt}"
    try:
        credits = estimate_marketing_plan_credits(
            plan,
            model=payload.model,
            resolution=payload.resolution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    project = MarketingVideoProject(
        user_id=current_user.id,
        source_asset_id=uuid.UUID(payload.source_asset_id),
        reference_assets_json=json.dumps(reference_assets, ensure_ascii=False),
        title=plan["title"],
        product_name=payload.product_name,
        idea=payload.idea,
        platform=payload.platform,
        market=payload.market,
        language=payload.language,
        duration=payload.duration,
        template_id=payload.template_id,
        mode="creative",
        continuity_json="{}",
        model=payload.model,
        resolution=payload.resolution,
        status="brief_ready",
        brief_json=json.dumps(plan, ensure_ascii=False),
        credits_estimated=credits,
        idempotency_key=key,
    )
    db.add(project)
    await db.flush()
    for item in plan["shots"]:
        db.add(
            MarketingVideoShot(
                project_id=project.id,
                position=item["position"],
                title=item["title"],
                purpose=item["purpose"],
                prompt=item["prompt"],
                source_text=item["prompt"],
                duration=item["duration"],
                status="planned",
            )
        )
    await current_user.deduct_credits(
        db,
        1,
        feature="marketing_video_plan",
        reference_type="marketing_video_project",
        reference_id=str(project.id),
        description="AI 营销方案与分镜",
    )
    await db.flush()
    return await _serialize_project(db, project)


@router.get("/projects", response_model=list[MarketingProjectResponse])
async def list_marketing_projects(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = (
        await db.execute(
            select(MarketingVideoProject)
            .where(MarketingVideoProject.user_id == current_user.id)
            .order_by(
                desc(MarketingVideoProject.created_at),
                desc(MarketingVideoProject.id),
            )
            .limit(limit)
        )
    ).scalars().all()
    return [await _serialize_project(db, project) for project in projects]


@router.get("/projects/{project_id}", response_model=MarketingProjectResponse)
async def get_marketing_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user.id)
    return await _serialize_project(db, project)


@router.post(
    "/projects/{project_id}/render",
    response_model=MarketingProjectResponse,
    status_code=202,
)
async def render_marketing_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user.id)
    try:
        await start_marketing_project(db, project, current_user)
    except InsufficientCreditsError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await _serialize_project(db, project)


@router.post("/projects/{project_id}/cancel", response_model=MarketingProjectResponse)
async def cancel_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user.id)
    if not await cancel_marketing_project(db, project):
        raise HTTPException(status_code=409, detail="当前营销视频项目无法取消")
    return await _serialize_project(db, project)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_marketing_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除终态营销项目，并清理项目镜头与本地视频文件。"""
    project = await _owned_project(db, project_id, current_user.id)
    if project.status == "rendering":
        raise HTTPException(status_code=409, detail="营销视频仍在生成，暂时不能删除")
    shots = await _project_shots(db, project)
    task_ids = [shot.video_task_id for shot in shots if shot.video_task_id]
    tasks = (
        await db.execute(
            select(VideoGenerationTask).where(
                VideoGenerationTask.id.in_(task_ids),
                VideoGenerationTask.user_id == current_user.id,
            )
        )
    ).scalars().all() if task_ids else []
    paths: list[Path] = []
    if project.final_storage_key:
        paths.append(_project_file_path(project.final_storage_key))
    for task in tasks:
        if task.storage_key:
            paths.append(_project_file_path(task.storage_key))

    for shot in shots:
        await db.delete(shot)
    await db.flush()
    await db.delete(project)
    await db.flush()
    for task in tasks:
        await db.delete(task)
    await db.flush()
    for path in paths:
        if path.is_file():
            path.unlink()
    return None


@router.get("/projects/{project_id}/file")
async def get_marketing_project_file(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project(db, project_id, current_user.id)
    if project.status != "succeeded" or not project.final_storage_key:
        raise HTTPException(status_code=404, detail="营销成片不存在")
    path = _project_file_path(project.final_storage_key)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="营销成片文件缺失，请重新生成或联系管理员",
        )
    return FileResponse(
        path,
        media_type=project.mime or "video/mp4",
        filename=_marketing_download_filename(project, "mp4"),
    )


async def _project_shots(
    db: AsyncSession,
    project: MarketingVideoProject,
) -> list[MarketingVideoShot]:
    return list(
        (
            await db.execute(
                select(MarketingVideoShot)
                .where(MarketingVideoShot.project_id == project.id)
                .order_by(MarketingVideoShot.position)
            )
        ).scalars().all()
    )


@router.get("/projects/{project_id}/subtitles")
async def download_marketing_subtitles(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按项目分镜实时生成 SRT，避免字幕与用户修改后的方案脱节。"""
    project = await _owned_project(db, project_id, current_user.id)
    brief = _parse_brief(project)
    if project.mode == "script" or brief.get("no_subtitles"):
        raise HTTPException(
            status_code=409,
            detail="专业分镜没有结构化字幕文本，不自动编造 SRT",
        )
    shots = await _project_shots(db, project)
    content = build_marketing_srt(
        brief,
        [
            {
                "position": shot.position,
                "title": shot.title,
                "duration": shot.duration,
            }
            for shot in shots
        ],
    )
    if not content:
        raise HTTPException(status_code=404, detail="当前项目没有可生成的字幕")
    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-subrip; charset=utf-8",
        headers={
            "Content-Disposition": _attachment_disposition(
                _marketing_download_filename(project, "srt")
            )
        },
    )


@router.post("/projects/{project_id}/voiceover")
async def generate_marketing_voiceover(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为项目脚本生成配音；供应商失败时不扣积分。"""
    project = await _owned_project(db, project_id, current_user.id)
    brief = _parse_brief(project)
    if project.mode == "script" or brief.get("no_dialogue"):
        raise HTTPException(
            status_code=409,
            detail="专业分镜没有结构化旁白文本，不自动编造配音",
        )
    narration = " ".join(
        item
        for item in (
            str(brief.get("hook") or "").strip(),
            str(brief.get("script") or "").strip(),
            str(brief.get("cta") or "").strip(),
        )
        if item
    )
    if not narration:
        raise HTTPException(status_code=400, detail="当前项目没有可配音的脚本")
    credits_cost = max(3, math.ceil(len(narration) / 100))
    if current_user.credits < credits_cost:
        raise HTTPException(
            status_code=402,
            detail=f"积分不足，本次配音生成需要 {credits_cost} 积分",
        )
    try:
        audio, media_type = await synthesize_minimax_tts(narration)
    except MiniMaxTTSNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except MiniMaxTTSError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    await current_user.deduct_credits(
        db,
        credits_cost,
        feature="marketing_voiceover",
        reference_type="marketing_video_project",
        reference_id=str(project.id),
        description="营销视频 AI 配音",
    )
    return Response(
        content=audio,
        media_type=media_type,
        headers={
            "Content-Disposition": _attachment_disposition(
                _marketing_download_filename(project, "mp3")
            ),
            "X-Credits-Charged": str(credits_cost),
        },
    )
